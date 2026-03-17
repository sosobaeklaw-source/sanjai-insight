"""
Alert Rules System
Monitors system metrics and triggers alerts based on thresholds.
Integrates with Telegram for notifications.
"""

import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import requests


@dataclass
class AlertRule:
    """Alert rule definition"""
    name: str
    condition: Callable[[sqlite3.Connection], bool]
    threshold: float
    severity: str  # INFO, WARNING, ERROR, CRITICAL
    cooldown_seconds: int  # Minimum time between alerts
    message_template: str
    metadata_extractor: Optional[Callable[[sqlite3.Connection], Dict[str, Any]]] = None


class AlertManager:
    """Manages alert rules and notifications"""

    def __init__(self, db_path: str, telegram_bot_token: Optional[str] = None,
                 telegram_chat_id: Optional[str] = None):
        self.db_path = db_path
        self.telegram_bot_token = telegram_bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = telegram_chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.rules: List[AlertRule] = []
        self._init_rules()

    def _init_rules(self):
        """Initialize built-in alert rules"""

        # Rule 1: Cost Overrun (24h)
        def cost_overrun_check(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("""
                SELECT COALESCE(SUM(cost_usd), 0) as total_cost
                FROM llm_calls
                WHERE created_at >= datetime('now', '-24 hours')
            """)
            result = cursor.fetchone()
            return result[0] > 10.0  # $10/day threshold

        def cost_overrun_metadata(conn: sqlite3.Connection) -> Dict[str, Any]:
            cursor = conn.execute("""
                SELECT
                    SUM(cost_usd) as total_cost,
                    COUNT(*) as call_count,
                    stage,
                    SUM(cost_usd) as stage_cost
                FROM llm_calls
                WHERE created_at >= datetime('now', '-24 hours')
                GROUP BY stage
                ORDER BY stage_cost DESC
                LIMIT 3
            """)
            rows = cursor.fetchall()
            total_cost = rows[0][0] if rows else 0
            top_stages = [{"stage": r[2], "cost": r[3]} for r in rows[:3]]
            return {"total_cost": total_cost, "top_stages": top_stages}

        self.rules.append(AlertRule(
            name="COST_OVERRUN_24H",
            condition=cost_overrun_check,
            threshold=10.0,
            severity="WARNING",
            cooldown_seconds=3600,  # 1 hour
            message_template="⚠️ 비용 초과: 24시간 비용이 ${total_cost:.2f}를 초과했습니다.",
            metadata_extractor=cost_overrun_metadata
        ))

        # Rule 2: Quality Degradation (7d validation pass rate < 80%)
        def quality_degradation_check(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("""
                SELECT
                    CAST(SUM(CASE WHEN validation_status = 'PASS' THEN 1 ELSE 0 END) AS FLOAT) /
                    CAST(COUNT(*) AS FLOAT) as pass_rate
                FROM strategy_packs
                WHERE created_at >= datetime('now', '-7 days')
                  AND validation_status IN ('PASS', 'FAIL')
            """)
            result = cursor.fetchone()
            return result[0] < 0.80 if result[0] is not None else False

        def quality_degradation_metadata(conn: sqlite3.Connection) -> Dict[str, Any]:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN validation_status = 'PASS' THEN 1 ELSE 0 END) as passed,
                    SUM(CASE WHEN validation_status = 'FAIL' THEN 1 ELSE 0 END) as failed
                FROM strategy_packs
                WHERE created_at >= datetime('now', '-7 days')
                  AND validation_status IN ('PASS', 'FAIL')
            """)
            result = cursor.fetchone()
            return {
                "total": result[0],
                "passed": result[1],
                "failed": result[2],
                "pass_rate": result[1] / result[0] if result[0] > 0 else 0
            }

        self.rules.append(AlertRule(
            name="QUALITY_DEGRADATION_7D",
            condition=quality_degradation_check,
            threshold=0.80,
            severity="ERROR",
            cooldown_seconds=7200,  # 2 hours
            message_template="🔴 품질 저하: 7일 검증 통과율이 {pass_rate:.1%}로 하락했습니다.",
            metadata_extractor=quality_degradation_metadata
        ))

        # Rule 3: Approval Rate Drop (7d < 70%)
        def approval_rate_drop_check(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("""
                SELECT
                    CAST(SUM(CASE WHEN decision = 'APPROVE' THEN 1 ELSE 0 END) AS FLOAT) /
                    CAST(COUNT(*) AS FLOAT) as approval_rate
                FROM approvals
                WHERE decided_at >= datetime('now', '-7 days')
            """)
            result = cursor.fetchone()
            return result[0] < 0.70 if result[0] is not None else False

        def approval_rate_metadata(conn: sqlite3.Connection) -> Dict[str, Any]:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN decision = 'APPROVE' THEN 1 ELSE 0 END) as approved,
                    SUM(CASE WHEN decision = 'REJECT' THEN 1 ELSE 0 END) as rejected,
                    SUM(CASE WHEN decision = 'DEFER' THEN 1 ELSE 0 END) as deferred
                FROM approvals
                WHERE decided_at >= datetime('now', '-7 days')
            """)
            result = cursor.fetchone()
            return {
                "total": result[0],
                "approved": result[1],
                "rejected": result[2],
                "deferred": result[3],
                "approval_rate": result[1] / result[0] if result[0] > 0 else 0
            }

        self.rules.append(AlertRule(
            name="APPROVAL_RATE_DROP_7D",
            condition=approval_rate_drop_check,
            threshold=0.70,
            severity="WARNING",
            cooldown_seconds=7200,
            message_template="📉 승인율 하락: 7일 승인율이 {approval_rate:.1%}로 하락했습니다.",
            metadata_extractor=approval_rate_metadata
        ))

        # Rule 4: High Latency (avg > 3000ms in 1h)
        def high_latency_check(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("""
                SELECT AVG(latency_ms) as avg_latency
                FROM llm_calls
                WHERE created_at >= datetime('now', '-1 hour')
                  AND latency_ms IS NOT NULL
            """)
            result = cursor.fetchone()
            return result[0] > 3000 if result[0] is not None else False

        def high_latency_metadata(conn: sqlite3.Connection) -> Dict[str, Any]:
            cursor = conn.execute("""
                SELECT
                    AVG(latency_ms) as avg_latency,
                    MAX(latency_ms) as max_latency,
                    COUNT(*) as call_count
                FROM llm_calls
                WHERE created_at >= datetime('now', '-1 hour')
                  AND latency_ms IS NOT NULL
            """)
            result = cursor.fetchone()
            return {
                "avg_latency_ms": result[0],
                "max_latency_ms": result[1],
                "call_count": result[2]
            }

        self.rules.append(AlertRule(
            name="HIGH_LATENCY_1H",
            condition=high_latency_check,
            threshold=3000,
            severity="WARNING",
            cooldown_seconds=1800,  # 30 min
            message_template="⏱️ 높은 지연: 1시간 평균 지연이 {avg_latency_ms:.0f}ms입니다.",
            metadata_extractor=high_latency_metadata
        ))

        # Rule 5: Database Size (> 500MB)
        def db_size_check(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            result = cursor.fetchone()
            size_mb = result[0] / (1024 * 1024) if result[0] else 0
            return size_mb > 500

        def db_size_metadata(conn: sqlite3.Connection) -> Dict[str, Any]:
            cursor = conn.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            result = cursor.fetchone()
            size_mb = result[0] / (1024 * 1024) if result[0] else 0
            return {"size_mb": size_mb}

        self.rules.append(AlertRule(
            name="DB_SIZE_LIMIT",
            condition=db_size_check,
            threshold=500,
            severity="WARNING",
            cooldown_seconds=21600,  # 6 hours
            message_template="💾 DB 크기 경고: 데이터베이스 크기가 {size_mb:.1f}MB입니다.",
            metadata_extractor=db_size_metadata
        ))

        # Rule 6: High Failure Rate (> 10% in 1h)
        def high_failure_rate_check(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("""
                SELECT
                    CAST(SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS FLOAT) /
                    CAST(COUNT(*) AS FLOAT) as failure_rate
                FROM runlogs
                WHERE started_at >= datetime('now', '-1 hour')
                  AND status IN ('COMPLETED', 'FAILED')
            """)
            result = cursor.fetchone()
            return result[0] > 0.10 if result[0] is not None else False

        def high_failure_rate_metadata(conn: sqlite3.Connection) -> Dict[str, Any]:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
                FROM runlogs
                WHERE started_at >= datetime('now', '-1 hour')
                  AND status IN ('COMPLETED', 'FAILED')
            """)
            result = cursor.fetchone()
            return {
                "total": result[0],
                "failed": result[1],
                "failure_rate": result[1] / result[0] if result[0] > 0 else 0
            }

        self.rules.append(AlertRule(
            name="HIGH_FAILURE_RATE_1H",
            condition=high_failure_rate_check,
            threshold=0.10,
            severity="ERROR",
            cooldown_seconds=3600,
            message_template="❌ 높은 실패율: 1시간 실행 실패율이 {failure_rate:.1%}입니다.",
            metadata_extractor=high_failure_rate_metadata
        ))

        # Rule 7: Crawler Failures (> 3 consecutive failures)
        def crawler_failure_check(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("""
                SELECT source_id, last_error
                FROM sources
                WHERE enabled = 1
                  AND last_error IS NOT NULL
                  AND (last_success_at IS NULL OR last_success_at < datetime('now', '-6 hours'))
            """)
            results = cursor.fetchall()
            return len(results) >= 3

        def crawler_failure_metadata(conn: sqlite3.Connection) -> Dict[str, Any]:
            cursor = conn.execute("""
                SELECT source_id, type, last_error, last_success_at
                FROM sources
                WHERE enabled = 1
                  AND last_error IS NOT NULL
                  AND (last_success_at IS NULL OR last_success_at < datetime('now', '-6 hours'))
            """)
            results = cursor.fetchall()
            return {
                "failed_sources": [
                    {
                        "source_id": r[0],
                        "type": r[1],
                        "last_error": r[2][:100] if r[2] else None,
                        "last_success_at": r[3]
                    }
                    for r in results
                ]
            }

        self.rules.append(AlertRule(
            name="CRAWLER_FAILURES",
            condition=crawler_failure_check,
            threshold=3,
            severity="ERROR",
            cooldown_seconds=7200,
            message_template="🕷️ 크롤러 실패: {failed_count}개 소스가 6시간 이상 실패 중입니다.",
            metadata_extractor=crawler_failure_metadata
        ))

        # Rule 8: Memory Warning (pending jobs > 50)
        def memory_warning_check(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("""
                SELECT COUNT(*) as pending_count
                FROM jobs
                WHERE status = 'PENDING'
            """)
            result = cursor.fetchone()
            return result[0] > 50

        def memory_warning_metadata(conn: sqlite3.Connection) -> Dict[str, Any]:
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as pending_count,
                    type,
                    COUNT(*) as type_count
                FROM jobs
                WHERE status = 'PENDING'
                GROUP BY type
                ORDER BY type_count DESC
            """)
            results = cursor.fetchall()
            return {
                "pending_count": results[0][0] if results else 0,
                "by_type": [{"type": r[1], "count": r[2]} for r in results]
            }

        self.rules.append(AlertRule(
            name="MEMORY_WARNING",
            condition=memory_warning_check,
            threshold=50,
            severity="WARNING",
            cooldown_seconds=3600,
            message_template="🧠 메모리 경고: {pending_count}개의 대기 중인 작업이 있습니다.",
            metadata_extractor=memory_warning_metadata
        ))

    def check_all_rules(self) -> List[Dict[str, Any]]:
        """Check all rules and return triggered alerts"""
        triggered_alerts = []

        with sqlite3.connect(self.db_path) as conn:
            for rule in self.rules:
                # Check cooldown
                if self._is_in_cooldown(conn, rule.name, rule.cooldown_seconds):
                    continue

                # Check condition
                try:
                    if rule.condition(conn):
                        # Extract metadata
                        metadata = {}
                        if rule.metadata_extractor:
                            metadata = rule.metadata_extractor(conn)

                        # Format message
                        message = rule.message_template.format(**metadata)

                        # Create alert
                        alert = self._create_alert(
                            conn, rule.name, rule.severity, message, metadata
                        )
                        triggered_alerts.append(alert)

                        # Send notification
                        self._send_notification(alert)

                except Exception as e:
                    print(f"Error checking rule {rule.name}: {e}")

        return triggered_alerts

    def _is_in_cooldown(self, conn: sqlite3.Connection, rule_name: str,
                        cooldown_seconds: int) -> bool:
        """Check if rule is in cooldown period"""
        cursor = conn.execute("""
            SELECT triggered_at
            FROM alerts
            WHERE rule_name = ?
              AND resolved = 0
            ORDER BY triggered_at DESC
            LIMIT 1
        """, (rule_name,))
        result = cursor.fetchone()

        if not result:
            return False

        last_trigger = datetime.fromisoformat(result[0])
        return (datetime.utcnow() - last_trigger).total_seconds() < cooldown_seconds

    def _create_alert(self, conn: sqlite3.Connection, rule_name: str,
                     severity: str, message: str,
                     metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Create alert record in database"""
        alert_id = str(uuid4())
        timestamp = datetime.utcnow().isoformat()

        conn.execute("""
            INSERT INTO alerts (alert_id, rule_name, severity, message,
                              metadata_json, triggered_at, resolved, notified)
            VALUES (?, ?, ?, ?, ?, ?, 0, 0)
        """, (alert_id, rule_name, severity, message,
              str(metadata), timestamp))
        conn.commit()

        return {
            "alert_id": alert_id,
            "rule_name": rule_name,
            "severity": severity,
            "message": message,
            "metadata": metadata,
            "triggered_at": timestamp
        }

    def _send_notification(self, alert: Dict[str, Any]):
        """Send Telegram notification"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return

        severity_emojis = {
            "INFO": "ℹ️",
            "WARNING": "⚠️",
            "ERROR": "🔴",
            "CRITICAL": "🚨"
        }

        emoji = severity_emojis.get(alert["severity"], "ℹ️")
        text = f"{emoji} *{alert['severity']}*\n\n{alert['message']}\n\n_Rule: {alert['rule_name']}_\n_Time: {alert['triggered_at']}_"

        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": self.telegram_chat_id,
                    "text": text,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )

            if response.status_code == 200:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        UPDATE alerts
                        SET notified = 1, notification_attempts = notification_attempts + 1
                        WHERE alert_id = ?
                    """, (alert["alert_id"],))
                    conn.commit()

        except Exception as e:
            print(f"Failed to send notification for {alert['alert_id']}: {e}")

    def resolve_alert(self, alert_id: str):
        """Mark alert as resolved"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE alerts
                SET resolved = 1, resolved_at = datetime('now')
                WHERE alert_id = ?
            """, (alert_id,))
            conn.commit()

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get all active (unresolved) alerts"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT alert_id, rule_name, severity, message, triggered_at
                FROM alerts
                WHERE resolved = 0
                ORDER BY triggered_at DESC
            """)
            return [
                {
                    "alert_id": r[0],
                    "rule_name": r[1],
                    "severity": r[2],
                    "message": r[3],
                    "triggered_at": r[4]
                }
                for r in cursor.fetchall()
            ]
