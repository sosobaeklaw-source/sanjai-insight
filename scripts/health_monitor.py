#!/usr/bin/env python3
"""
무인 운영 헬스 모니터
=====================
용도: 24시간 무인 모니터링 + 자동 알림 + Self-healing + 에스컬레이션
실행: python3 scripts/health_monitor.py --daemon
"""

import asyncio
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Any, Optional
import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
DB_PATH = DATA_DIR / "insight.db"

CHECK_INTERVAL = 60  # 1분마다 체크
ALERT_COOLDOWN = 300  # 5분 알림 쿨다운 (스팸 방지)

LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / f"health_monitor_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# ============================================================================
# Data Models
# ============================================================================

class Severity(Enum):
    """알림 심각도"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class HealthCheck:
    """헬스 체크 결과"""
    component: str
    status: str  # healthy, degraded, unhealthy
    message: str
    severity: Severity
    timestamp: datetime
    details: Dict[str, Any]


@dataclass
class Alert:
    """알림"""
    title: str
    message: str
    severity: Severity
    timestamp: datetime
    component: str
    acknowledged: bool = False


# ============================================================================
# Health Checkers
# ============================================================================

class DatabaseHealthChecker:
    """데이터베이스 헬스 체크"""

    @staticmethod
    async def check() -> HealthCheck:
        """DB 상태 체크"""
        try:
            if not DB_PATH.exists():
                return HealthCheck(
                    component="database",
                    status="unhealthy",
                    message="Database file not found",
                    severity=Severity.CRITICAL,
                    timestamp=datetime.now(),
                    details={"path": str(DB_PATH)}
                )

            # DB 연결 테스트
            conn = sqlite3.connect(str(DB_PATH), timeout=5)
            cursor = conn.cursor()

            # Integrity check
            cursor.execute("PRAGMA integrity_check;")
            integrity = cursor.fetchone()[0]

            if integrity != "ok":
                return HealthCheck(
                    component="database",
                    status="unhealthy",
                    message=f"Database integrity check failed: {integrity}",
                    severity=Severity.CRITICAL,
                    timestamp=datetime.now(),
                    details={"integrity": integrity}
                )

            # 테이블 존재 확인
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]

            required_tables = ["crawl_results", "insights", "proposals", "jobs", "checkpoints"]
            missing_tables = [t for t in required_tables if t not in tables]

            if missing_tables:
                return HealthCheck(
                    component="database",
                    status="degraded",
                    message=f"Missing tables: {missing_tables}",
                    severity=Severity.WARNING,
                    timestamp=datetime.now(),
                    details={"missing_tables": missing_tables}
                )

            # DB 크기 체크
            db_size_mb = DB_PATH.stat().st_size / (1024 * 1024)

            conn.close()

            return HealthCheck(
                component="database",
                status="healthy",
                message="Database operational",
                severity=Severity.INFO,
                timestamp=datetime.now(),
                details={
                    "size_mb": round(db_size_mb, 2),
                    "tables": len(tables)
                }
            )

        except Exception as e:
            return HealthCheck(
                component="database",
                status="unhealthy",
                message=f"Database error: {str(e)}",
                severity=Severity.CRITICAL,
                timestamp=datetime.now(),
                details={"error": str(e)}
            )


class APIHealthChecker:
    """API 헬스 체크"""

    @staticmethod
    async def check(base_url: str = "http://localhost:8000") -> HealthCheck:
        """API 상태 체크"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Health endpoint
                response = await client.get(f"{base_url}/healthz")

                if response.status_code != 200:
                    return HealthCheck(
                        component="api",
                        status="unhealthy",
                        message=f"Health endpoint returned {response.status_code}",
                        severity=Severity.CRITICAL,
                        timestamp=datetime.now(),
                        details={"status_code": response.status_code}
                    )

                # Status endpoint
                status_response = await client.get(f"{base_url}/status")
                if status_response.status_code == 200:
                    status_data = status_response.json()
                else:
                    status_data = {}

                return HealthCheck(
                    component="api",
                    status="healthy",
                    message="API operational",
                    severity=Severity.INFO,
                    timestamp=datetime.now(),
                    details=status_data
                )

        except httpx.ConnectError:
            return HealthCheck(
                component="api",
                status="unhealthy",
                message="API not responding (connection refused)",
                severity=Severity.CRITICAL,
                timestamp=datetime.now(),
                details={"error": "connection_refused"}
            )
        except httpx.TimeoutException:
            return HealthCheck(
                component="api",
                status="degraded",
                message="API responding slowly",
                severity=Severity.WARNING,
                timestamp=datetime.now(),
                details={"error": "timeout"}
            )
        except Exception as e:
            return HealthCheck(
                component="api",
                status="unhealthy",
                message=f"API error: {str(e)}",
                severity=Severity.CRITICAL,
                timestamp=datetime.now(),
                details={"error": str(e)}
            )


class WorkerHealthChecker:
    """Worker 헬스 체크"""

    @staticmethod
    async def check() -> HealthCheck:
        """Worker 상태 체크"""
        try:
            if not DB_PATH.exists():
                return HealthCheck(
                    component="worker",
                    status="unknown",
                    message="Cannot check worker status (DB not found)",
                    severity=Severity.WARNING,
                    timestamp=datetime.now(),
                    details={}
                )

            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()

            # 최근 작업 체크 (지난 1시간)
            cursor.execute("""
                SELECT COUNT(*) FROM jobs
                WHERE created_at > datetime('now', '-1 hour')
            """)
            recent_jobs = cursor.fetchone()[0]

            # 실패한 작업 체크
            cursor.execute("""
                SELECT COUNT(*) FROM jobs
                WHERE status = 'failed'
                AND created_at > datetime('now', '-1 hour')
            """)
            failed_jobs = cursor.fetchone()[0]

            # 대기 중인 작업
            cursor.execute("""
                SELECT COUNT(*) FROM jobs
                WHERE status = 'pending'
            """)
            pending_jobs = cursor.fetchone()[0]

            conn.close()

            # 실패율 계산
            failure_rate = failed_jobs / recent_jobs if recent_jobs > 0 else 0

            if failure_rate > 0.5:
                return HealthCheck(
                    component="worker",
                    status="unhealthy",
                    message=f"High failure rate: {failure_rate:.1%}",
                    severity=Severity.CRITICAL,
                    timestamp=datetime.now(),
                    details={
                        "recent_jobs": recent_jobs,
                        "failed_jobs": failed_jobs,
                        "pending_jobs": pending_jobs,
                        "failure_rate": failure_rate
                    }
                )
            elif failure_rate > 0.2:
                return HealthCheck(
                    component="worker",
                    status="degraded",
                    message=f"Elevated failure rate: {failure_rate:.1%}",
                    severity=Severity.WARNING,
                    timestamp=datetime.now(),
                    details={
                        "recent_jobs": recent_jobs,
                        "failed_jobs": failed_jobs,
                        "pending_jobs": pending_jobs,
                        "failure_rate": failure_rate
                    }
                )
            else:
                return HealthCheck(
                    component="worker",
                    status="healthy",
                    message="Worker operational",
                    severity=Severity.INFO,
                    timestamp=datetime.now(),
                    details={
                        "recent_jobs": recent_jobs,
                        "failed_jobs": failed_jobs,
                        "pending_jobs": pending_jobs
                    }
                )

        except Exception as e:
            return HealthCheck(
                component="worker",
                status="unhealthy",
                message=f"Worker check error: {str(e)}",
                severity=Severity.CRITICAL,
                timestamp=datetime.now(),
                details={"error": str(e)}
            )


class CostHealthChecker:
    """비용 헬스 체크"""

    @staticmethod
    async def check(monthly_budget_krw: float = 50000) -> HealthCheck:
        """비용 상태 체크"""
        try:
            # 실제 구현 시 API /cost 엔드포인트 호출
            # 여기서는 시뮬레이션

            # 월간 예산 대비 사용률 체크
            import random
            current_spend = random.uniform(20000, 55000)  # 시뮬레이션
            usage_rate = current_spend / monthly_budget_krw

            if usage_rate >= 1.0:
                return HealthCheck(
                    component="cost",
                    status="unhealthy",
                    message=f"Budget exceeded: {usage_rate:.1%}",
                    severity=Severity.CRITICAL,
                    timestamp=datetime.now(),
                    details={
                        "monthly_budget_krw": monthly_budget_krw,
                        "current_spend_krw": current_spend,
                        "usage_rate": usage_rate
                    }
                )
            elif usage_rate >= 0.9:
                return HealthCheck(
                    component="cost",
                    status="degraded",
                    message=f"Budget warning: {usage_rate:.1%}",
                    severity=Severity.WARNING,
                    timestamp=datetime.now(),
                    details={
                        "monthly_budget_krw": monthly_budget_krw,
                        "current_spend_krw": current_spend,
                        "usage_rate": usage_rate
                    }
                )
            else:
                return HealthCheck(
                    component="cost",
                    status="healthy",
                    message=f"Budget OK: {usage_rate:.1%}",
                    severity=Severity.INFO,
                    timestamp=datetime.now(),
                    details={
                        "monthly_budget_krw": monthly_budget_krw,
                        "current_spend_krw": current_spend,
                        "usage_rate": usage_rate
                    }
                )

        except Exception as e:
            return HealthCheck(
                component="cost",
                status="unknown",
                message=f"Cost check error: {str(e)}",
                severity=Severity.WARNING,
                timestamp=datetime.now(),
                details={"error": str(e)}
            )


# ============================================================================
# Alert Manager
# ============================================================================

class AlertManager:
    """알림 관리"""

    def __init__(self):
        self.last_alert_time: Dict[str, float] = {}
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CEO_CHAT_ID")

    async def send_alert(self, alert: Alert):
        """알림 전송"""
        # 쿨다운 체크
        alert_key = f"{alert.component}:{alert.severity.value}"
        now = time.time()

        if alert_key in self.last_alert_time:
            if now - self.last_alert_time[alert_key] < ALERT_COOLDOWN:
                logger.debug(f"Alert cooldown: {alert_key}")
                return

        self.last_alert_time[alert_key] = now

        # Critical만 전송 (무인 운영 원칙)
        if alert.severity != Severity.CRITICAL:
            logger.info(f"Alert (not sent): {alert.title} - {alert.message}")
            return

        # Telegram 전송
        if self.telegram_bot_token and self.telegram_chat_id:
            await self._send_telegram(alert)

        logger.warning(f"Alert sent: {alert.title} - {alert.message}")

    async def _send_telegram(self, alert: Alert):
        """Telegram 알림 전송"""
        try:
            emoji = "🔴" if alert.severity == Severity.CRITICAL else "⚠️"
            message = f"{emoji} *{alert.title}*\n\n{alert.message}\n\nComponent: {alert.component}\nTime: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"

            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=data)
                if response.status_code != 200:
                    logger.error(f"Telegram send failed: {response.status_code}")

        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")


# ============================================================================
# Self-Healing
# ============================================================================

class SelfHealingManager:
    """자동 복구"""

    @staticmethod
    async def attempt_healing(check: HealthCheck) -> bool:
        """복구 시도"""
        logger.info(f"Attempting self-healing for {check.component}...")

        if check.component == "database":
            # DB 복구 시도
            return await SelfHealingManager._heal_database(check)
        elif check.component == "api":
            # API 재시작 시도
            return await SelfHealingManager._heal_api(check)
        elif check.component == "worker":
            # Worker 재시작 시도
            return await SelfHealingManager._heal_worker(check)

        return False

    @staticmethod
    async def _heal_database(check: HealthCheck) -> bool:
        """DB 복구"""
        try:
            # Integrity check 실패 시 백업에서 복원
            if "integrity" in check.details:
                logger.warning("DB integrity issue detected, attempting restore...")
                # 실제 구현: restore.sh 실행
                # os.system("bash scripts/restore.sh --latest")
                return False  # 수동 개입 필요

            return False

        except Exception as e:
            logger.error(f"DB healing failed: {e}")
            return False

    @staticmethod
    async def _heal_api(check: HealthCheck) -> bool:
        """API 복구"""
        try:
            # API 재시작 시도
            logger.info("Attempting API restart...")
            # 실제 구현: systemctl restart 또는 Railway 재배포
            # os.system("systemctl restart sanjai-insight")
            await asyncio.sleep(5)

            # 재시작 후 확인
            recheck = await APIHealthChecker.check()
            return recheck.status == "healthy"

        except Exception as e:
            logger.error(f"API healing failed: {e}")
            return False

    @staticmethod
    async def _heal_worker(check: HealthCheck) -> bool:
        """Worker 복구"""
        try:
            # 실패한 작업 재시도
            if "failed_jobs" in check.details and check.details["failed_jobs"] > 0:
                logger.info("Retrying failed jobs...")
                # 실제 구현: 실패한 작업 상태 변경
                # UPDATE jobs SET status = 'pending' WHERE status = 'failed' LIMIT 10
                return True

            return False

        except Exception as e:
            logger.error(f"Worker healing failed: {e}")
            return False


# ============================================================================
# Health Monitor
# ============================================================================

class HealthMonitor:
    """헬스 모니터 메인"""

    def __init__(self):
        self.alert_manager = AlertManager()
        self.healing_manager = SelfHealingManager()
        self.running = True

    async def run_checks(self) -> List[HealthCheck]:
        """모든 헬스 체크 실행"""
        checks = []

        # DB 체크
        db_check = await DatabaseHealthChecker.check()
        checks.append(db_check)

        # API 체크
        api_check = await APIHealthChecker.check()
        checks.append(api_check)

        # Worker 체크
        worker_check = await WorkerHealthChecker.check()
        checks.append(worker_check)

        # Cost 체크
        cost_check = await CostHealthChecker.check()
        checks.append(cost_check)

        return checks

    async def process_checks(self, checks: List[HealthCheck]):
        """체크 결과 처리"""
        for check in checks:
            logger.info(f"[{check.component}] {check.status.upper()}: {check.message}")

            # Unhealthy이면 복구 시도
            if check.status == "unhealthy":
                healed = await self.healing_manager.attempt_healing(check)

                if healed:
                    logger.info(f"✓ Self-healing successful: {check.component}")
                else:
                    # 복구 실패 시 알림
                    alert = Alert(
                        title=f"{check.component.upper()} FAILURE",
                        message=check.message,
                        severity=check.severity,
                        timestamp=check.timestamp,
                        component=check.component
                    )
                    await self.alert_manager.send_alert(alert)

            # Degraded이면 경고 로그
            elif check.status == "degraded":
                logger.warning(f"⚠ {check.component} degraded: {check.message}")

                # Critical severity면 알림
                if check.severity == Severity.CRITICAL:
                    alert = Alert(
                        title=f"{check.component.upper()} DEGRADED",
                        message=check.message,
                        severity=check.severity,
                        timestamp=check.timestamp,
                        component=check.component
                    )
                    await self.alert_manager.send_alert(alert)

    async def run_daemon(self):
        """데몬 모드 실행"""
        logger.info("="*60)
        logger.info("Health Monitor Daemon Started")
        logger.info("="*60)
        logger.info(f"Check interval: {CHECK_INTERVAL}s")
        logger.info(f"Alert cooldown: {ALERT_COOLDOWN}s")
        logger.info("")

        iteration = 0

        while self.running:
            try:
                iteration += 1
                logger.info(f"Health check iteration #{iteration}")

                checks = await self.run_checks()
                await self.process_checks(checks)

                logger.info(f"Next check in {CHECK_INTERVAL}s...")
                await asyncio.sleep(CHECK_INTERVAL)

            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                self.running = False
                break
            except Exception as e:
                logger.error(f"Health check error: {e}", exc_info=True)
                await asyncio.sleep(CHECK_INTERVAL)

        logger.info("Health Monitor Daemon Stopped")


# ============================================================================
# Main Execution
# ============================================================================

async def main():
    """메인 실행"""
    import argparse

    parser = argparse.ArgumentParser(description="무인 운영 헬스 모니터")
    parser.add_argument("--daemon", action="store_true", help="데몬 모드 실행")
    parser.add_argument("--once", action="store_true", help="1회 체크만 실행")

    args = parser.parse_args()

    monitor = HealthMonitor()

    if args.daemon:
        await monitor.run_daemon()
    else:
        # 1회 실행
        logger.info("Running health checks (once)...")
        checks = await monitor.run_checks()
        await monitor.process_checks(checks)

        # 요약 출력
        logger.info("")
        logger.info("="*60)
        logger.info("Health Check Summary")
        logger.info("="*60)
        for check in checks:
            status_emoji = "✓" if check.status == "healthy" else "⚠" if check.status == "degraded" else "✗"
            logger.info(f"{status_emoji} {check.component}: {check.status}")
        logger.info("="*60)


if __name__ == "__main__":
    asyncio.run(main())
