"""
Self-Diagnose Engine - 자기진단 및 자기개선
시스템 상태 모니터링, 이상 감지, 자동 조정
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

import aiosqlite

from ..models import EventType
from ..core.events import EventLogger
from ..core.checkpoint import CheckpointManager
from ..core.termination import TerminationChecker

logger = logging.getLogger(__name__)


class SelfDiagnoseEngine:
    """Self-Diagnose Engine - 시스템 자가진단 및 개선"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.event_logger = EventLogger(db_path)

    async def run(
        self,
        correlation_id: str,
        payload: Dict[str, Any],
        ctx: Dict[str, Any],
        checker: TerminationChecker,
        checkpoint_manager: CheckpointManager,
        event_logger: EventLogger,
    ) -> Dict[str, Any]:
        """
        Self-Diagnose 실행 (Worker 핸들러)

        Args:
            correlation_id: 실행 추적 ID
            payload: {checks: ["health", "cost", "quality", "performance"]}
            ctx: 체크포인트 컨텍스트
            checker: 종료 조건 체크
            checkpoint_manager: 체크포인트 관리
            event_logger: 이벤트 로거

        Returns:
            {
                "overall_health": "HEALTHY" | "DEGRADED" | "CRITICAL",
                "checks": {...},
                "issues": [...],
                "recommendations": [...]
            }
        """
        checks_to_run = payload.get(
            "checks", ["health", "cost", "quality", "performance"]
        )

        # 시작 이벤트
        await event_logger.log(
            EventType.DIAGNOSE_START,
            correlation_id,
            {"checks": checks_to_run},
        )

        results = {
            "overall_health": "HEALTHY",
            "checks": {},
            "issues": [],
            "recommendations": [],
        }

        # 각 체크 실행
        for check_name in checks_to_run:
            # 종료 조건 체크
            should_terminate, reason = checker.check()
            if should_terminate:
                logger.warning(f"[SelfDiagnose] Termination: {reason}")
                await event_logger.log(
                    EventType.TERMINATION,
                    correlation_id,
                    {"reason": reason, "stage": "DIAGNOSE"},
                )
                break

            try:
                logger.info(f"[SelfDiagnose] Running check: {check_name}")

                if check_name == "health":
                    check_result = await self._check_health()
                elif check_name == "cost":
                    check_result = await self._check_cost()
                elif check_name == "quality":
                    check_result = await self._check_quality()
                elif check_name == "performance":
                    check_result = await self._check_performance()
                else:
                    logger.warning(f"[SelfDiagnose] Unknown check: {check_name}")
                    continue

                results["checks"][check_name] = check_result

                # 이슈 수집
                if check_result.get("issues"):
                    results["issues"].extend(check_result["issues"])

                # 권고사항 수집
                if check_result.get("recommendations"):
                    results["recommendations"].extend(check_result["recommendations"])

                # 체크포인트 저장
                ctx["diagnose_progress"] = {
                    "completed_checks": list(results["checks"].keys()),
                    "issues_count": len(results["issues"]),
                }
                await checkpoint_manager.save(correlation_id, "DIAGNOSE", ctx)

            except Exception as e:
                logger.error(f"[SelfDiagnose] Error in check {check_name}: {e}")
                await event_logger.log(
                    EventType.ERROR,
                    correlation_id,
                    {"error": str(e), "check": check_name, "stage": "DIAGNOSE"},
                )
                continue

        # 전체 건강도 평가
        results["overall_health"] = self._evaluate_overall_health(results)

        # 자동 개선 조치 (선택적)
        if payload.get("auto_fix", False):
            await self._apply_auto_fixes(results, correlation_id, event_logger)

        # 완료 이벤트
        await event_logger.log(
            EventType.DIAGNOSE_END,
            correlation_id,
            {
                "overall_health": results["overall_health"],
                "issues_count": len(results["issues"]),
                "recommendations_count": len(results["recommendations"]),
            },
        )

        return results

    async def _check_health(self) -> Dict[str, Any]:
        """시스템 건강도 체크"""
        result = {
            "status": "PASS",
            "issues": [],
            "recommendations": [],
            "metrics": {},
        }

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. DB 상태
            try:
                cursor = await db.execute("SELECT 1")
                await cursor.fetchone()
                result["metrics"]["db_connected"] = True
            except Exception as e:
                result["status"] = "FAIL"
                result["issues"].append(
                    {"severity": "CRITICAL", "message": f"DB connection failed: {e}"}
                )
                result["metrics"]["db_connected"] = False

            # 2. 최근 성공 실행 확인 (24시간 이내)
            cursor = await db.execute(
                """
                SELECT MAX(started_at) as last_run
                FROM runlogs
                WHERE status = 'COMPLETED'
                """
            )
            row = await cursor.fetchone()
            if row and row["last_run"]:
                last_run = datetime.fromisoformat(row["last_run"])
                hours_since = (datetime.now() - last_run).total_seconds() / 3600
                result["metrics"]["hours_since_last_success"] = hours_since

                if hours_since > 48:
                    result["status"] = "FAIL"
                    result["issues"].append(
                        {
                            "severity": "HIGH",
                            "message": f"No successful run in {hours_since:.1f} hours",
                        }
                    )
                    result["recommendations"].append(
                        "Check job scheduler and worker status"
                    )
            else:
                result["issues"].append(
                    {"severity": "MEDIUM", "message": "No successful runs found"}
                )

            # 3. 실패 작업 확인
            cursor = await db.execute(
                """
                SELECT COUNT(*) as cnt FROM jobs
                WHERE status = 'FAILED'
                AND created_at >= datetime('now', '-24 hours')
                """
            )
            row = await cursor.fetchone()
            failed_jobs = row["cnt"] if row else 0
            result["metrics"]["failed_jobs_24h"] = failed_jobs

            if failed_jobs > 5:
                result["status"] = "FAIL"
                result["issues"].append(
                    {
                        "severity": "HIGH",
                        "message": f"{failed_jobs} failed jobs in last 24h",
                    }
                )
                result["recommendations"].append("Investigate job failure patterns")

            # 4. 활성 실행 확인 (장시간 running 상태)
            cursor = await db.execute(
                """
                SELECT correlation_id, started_at FROM runlogs
                WHERE status = 'RUNNING'
                AND started_at < datetime('now', '-2 hours')
                """
            )
            stuck_runs = await cursor.fetchall()
            if stuck_runs:
                result["issues"].append(
                    {
                        "severity": "MEDIUM",
                        "message": f"{len(stuck_runs)} runs stuck for >2 hours",
                    }
                )
                result["recommendations"].append("Consider terminating stuck runs")

        return result

    async def _check_cost(self) -> Dict[str, Any]:
        """비용 추적 및 임계값 체크"""
        result = {
            "status": "PASS",
            "issues": [],
            "recommendations": [],
            "metrics": {},
        }

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. 24시간 비용
            cursor = await db.execute(
                """
                SELECT SUM(cost_usd) as total FROM llm_calls
                WHERE created_at >= datetime('now', '-24 hours')
                """
            )
            row = await cursor.fetchone()
            cost_24h = row["total"] if row and row["total"] else 0.0
            result["metrics"]["cost_24h_usd"] = cost_24h

            # 임계값 체크 (PRD: $5/day 목표)
            if cost_24h > 10.0:
                result["status"] = "FAIL"
                result["issues"].append(
                    {
                        "severity": "CRITICAL",
                        "message": f"Daily cost ${cost_24h:.2f} exceeds $10 threshold",
                    }
                )
                result["recommendations"].append(
                    "Review LLM call patterns and consider reducing frequency"
                )
            elif cost_24h > 5.0:
                result["issues"].append(
                    {
                        "severity": "MEDIUM",
                        "message": f"Daily cost ${cost_24h:.2f} above $5 target",
                    }
                )

            # 2. Stage별 비용 분석
            cursor = await db.execute(
                """
                SELECT stage, SUM(cost_usd) as total, COUNT(*) as calls
                FROM llm_calls
                WHERE created_at >= datetime('now', '-24 hours')
                GROUP BY stage
                """
            )
            stage_costs = await cursor.fetchall()
            result["metrics"]["cost_by_stage"] = [
                {
                    "stage": row["stage"],
                    "cost_usd": row["total"],
                    "calls": row["calls"],
                }
                for row in stage_costs
            ]

            # 3. 평균 호출 비용
            cursor = await db.execute(
                """
                SELECT AVG(cost_usd) as avg_cost FROM llm_calls
                WHERE created_at >= datetime('now', '-24 hours')
                """
            )
            row = await cursor.fetchone()
            avg_cost = row["avg_cost"] if row and row["avg_cost"] else 0.0
            result["metrics"]["avg_cost_per_call"] = avg_cost

            if avg_cost > 0.5:
                result["recommendations"].append(
                    f"Average cost per call (${avg_cost:.3f}) is high - consider using smaller models"
                )

        return result

    async def _check_quality(self) -> Dict[str, Any]:
        """인사이트 품질 체크"""
        result = {
            "status": "PASS",
            "issues": [],
            "recommendations": [],
            "metrics": {},
        }

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. 최근 인사이트 생성률
            cursor = await db.execute(
                """
                SELECT COUNT(*) as cnt FROM insights
                WHERE created_at >= datetime('now', '-24 hours')
                """
            )
            row = await cursor.fetchone()
            insights_24h = row["cnt"] if row else 0
            result["metrics"]["insights_24h"] = insights_24h

            # PRD 목표: 5-10개/일
            if insights_24h < 3:
                result["issues"].append(
                    {
                        "severity": "MEDIUM",
                        "message": f"Only {insights_24h} insights generated in 24h (target: 5-10)",
                    }
                )
                result["recommendations"].append(
                    "Increase watch frequency or expand data sources"
                )

            # 2. Evidence 바인딩 실패율
            cursor = await db.execute(
                """
                SELECT
                    SUM(CASE WHEN type = 'INSIGHT_REJECTED' THEN 1 ELSE 0 END) as rejected,
                    SUM(CASE WHEN type = 'INSIGHT_CREATED' THEN 1 ELSE 0 END) as created
                FROM events
                WHERE created_at >= datetime('now', '-24 hours')
                AND type IN ('INSIGHT_CREATED', 'INSIGHT_REJECTED')
                """
            )
            row = await cursor.fetchone()
            rejected = row["rejected"] if row and row["rejected"] else 0
            created = row["created"] if row and row["created"] else 0
            total = rejected + created

            if total > 0:
                rejection_rate = rejected / total
                result["metrics"]["rejection_rate"] = rejection_rate

                if rejection_rate > 0.5:
                    result["issues"].append(
                        {
                            "severity": "HIGH",
                            "message": f"Evidence validation rejection rate {rejection_rate:.1%}",
                        }
                    )
                    result["recommendations"].append(
                        "Review LLM prompts to ensure evidence citation requirements are clear"
                    )

            # 3. 평균 confidence 점수
            cursor = await db.execute(
                """
                SELECT AVG(confidence) as avg_conf FROM insights
                WHERE created_at >= datetime('now', '-7 days')
                """
            )
            row = await cursor.fetchone()
            avg_confidence = row["avg_conf"] if row and row["avg_conf"] else 0.0
            result["metrics"]["avg_confidence"] = avg_confidence

            if avg_confidence < 0.7:
                result["issues"].append(
                    {
                        "severity": "MEDIUM",
                        "message": f"Average confidence {avg_confidence:.2f} below 0.7 target",
                    }
                )
                result["recommendations"].append(
                    "Improve data quality or adjust confidence thresholds"
                )

            # 4. 승인률
            cursor = await db.execute(
                """
                SELECT
                    SUM(CASE WHEN response = 'ACCEPTED' THEN 1 ELSE 0 END) as accepted,
                    COUNT(*) as total
                FROM proposals
                WHERE created_at >= datetime('now', '-7 days')
                AND response != 'PENDING'
                """
            )
            row = await cursor.fetchone()
            if row and row["total"] and row["total"] > 0:
                acceptance_rate = row["accepted"] / row["total"]
                result["metrics"]["acceptance_rate"] = acceptance_rate

                if acceptance_rate < 0.5:
                    result["issues"].append(
                        {
                            "severity": "MEDIUM",
                            "message": f"Proposal acceptance rate {acceptance_rate:.1%} below 50%",
                        }
                    )
                    result["recommendations"].append(
                        "Review insight relevance and presentation quality"
                    )

        return result

    async def _check_performance(self) -> Dict[str, Any]:
        """성능 지표 체크"""
        result = {
            "status": "PASS",
            "issues": [],
            "recommendations": [],
            "metrics": {},
        }

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. 평균 LLM 응답 시간
            cursor = await db.execute(
                """
                SELECT AVG(latency_ms) as avg_latency FROM llm_calls
                WHERE created_at >= datetime('now', '-24 hours')
                """
            )
            row = await cursor.fetchone()
            avg_latency = row["avg_latency"] if row and row["avg_latency"] else 0.0
            result["metrics"]["avg_llm_latency_ms"] = avg_latency

            if avg_latency > 10000:  # 10초
                result["issues"].append(
                    {
                        "severity": "MEDIUM",
                        "message": f"Average LLM latency {avg_latency/1000:.1f}s is high",
                    }
                )
                result["recommendations"].append(
                    "Consider using faster models or implementing caching"
                )

            # 2. 평균 job 실행 시간
            cursor = await db.execute(
                """
                SELECT AVG(
                    CAST((julianday(ended_at) - julianday(started_at)) * 86400 AS INTEGER)
                ) as avg_duration
                FROM runlogs
                WHERE status = 'COMPLETED'
                AND ended_at IS NOT NULL
                AND started_at >= datetime('now', '-7 days')
                """
            )
            row = await cursor.fetchone()
            avg_duration = row["avg_duration"] if row and row["avg_duration"] else 0
            result["metrics"]["avg_job_duration_sec"] = avg_duration

            if avg_duration > 300:  # 5분
                result["recommendations"].append(
                    f"Average job duration {avg_duration}s - consider optimization"
                )

            # 3. DB 크기
            cursor = await db.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            row = await cursor.fetchone()
            if row:
                db_size_mb = row[0] / (1024 * 1024)
                result["metrics"]["db_size_mb"] = db_size_mb

                if db_size_mb > 1000:  # 1GB
                    result["issues"].append(
                        {
                            "severity": "MEDIUM",
                            "message": f"DB size {db_size_mb:.1f}MB - consider archiving old data",
                        }
                    )
                    result["recommendations"].append("Implement data archival strategy")

            # 4. 인덱싱 성능
            cursor = await db.execute(
                """
                SELECT COUNT(*) as cnt FROM vault_chunks
                WHERE created_at >= datetime('now', '-24 hours')
                """
            )
            row = await cursor.fetchone()
            chunks_indexed_24h = row["cnt"] if row else 0
            result["metrics"]["chunks_indexed_24h"] = chunks_indexed_24h

        return result

    def _evaluate_overall_health(self, results: Dict[str, Any]) -> str:
        """전체 건강도 평가"""
        critical_count = 0
        high_count = 0

        for issue in results["issues"]:
            severity = issue.get("severity", "MEDIUM")
            if severity == "CRITICAL":
                critical_count += 1
            elif severity == "HIGH":
                high_count += 1

        if critical_count > 0:
            return "CRITICAL"
        elif high_count >= 2:
            return "DEGRADED"
        elif len(results["issues"]) > 5:
            return "DEGRADED"
        else:
            return "HEALTHY"

    async def _apply_auto_fixes(
        self,
        results: Dict[str, Any],
        correlation_id: str,
        event_logger: EventLogger,
    ):
        """자동 개선 조치 적용"""
        fixes_applied = []

        # 1. 장시간 실행 중인 작업 종료
        if any(
            "stuck" in issue.get("message", "").lower() for issue in results["issues"]
        ):
            try:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute(
                        """
                        UPDATE runlogs SET
                            status = 'FAILED',
                            meta_json = json_set(COALESCE(meta_json, '{}'), '$.error', 'Auto-terminated (stuck >2h)')
                        WHERE status = 'RUNNING'
                        AND started_at < datetime('now', '-2 hours')
                        """
                    )
                    await db.commit()
                    fixes_applied.append("Terminated stuck runs")
            except Exception as e:
                logger.error(f"[SelfDiagnose] Failed to terminate stuck runs: {e}")

        # 2. 오래된 이벤트 로그 정리 (30일 이상)
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    DELETE FROM events
                    WHERE created_at < datetime('now', '-30 days')
                    """
                )
                deleted = cursor.rowcount
                await db.commit()
                if deleted > 0:
                    fixes_applied.append(f"Cleaned {deleted} old event logs")
        except Exception as e:
            logger.error(f"[SelfDiagnose] Failed to clean old logs: {e}")

        # 로그
        if fixes_applied:
            await event_logger.log(
                EventType.AUTO_FIX_APPLIED,
                correlation_id,
                {"fixes": fixes_applied},
            )
            logger.info(f"[SelfDiagnose] Applied fixes: {fixes_applied}")
