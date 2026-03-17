"""
Threshold Optimizer
ROC curve 기반 최적 threshold 계산 + config/thresholds.yaml 자동 업데이트
"""

import logging
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiosqlite
import yaml

logger = logging.getLogger(__name__)


class ThresholdOptimizer:
    """
    프로토타입 결과 분석 → 최적 threshold 계산 → thresholds.yaml 업데이트

    분석 대상:
    - insights: confidence_threshold 최적화
    - proposals: acceptance_rate 기반 조정
    - crawlers: circuit_breaker 패턴 분석
    """

    def __init__(
        self, db_path: str, config_path: str = "config/thresholds.yaml"
    ):
        self.db_path = db_path
        self.config_path = config_path

    async def analyze_prototype_results(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> dict[str, Any]:
        """
        프로토타입 결과 분석

        Returns:
            {
                "insight_metrics": {...},
                "proposal_metrics": {...},
                "crawler_metrics": {...},
                "cost_metrics": {...}
            }
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Insight 분석
            insight_metrics = await self._analyze_insights(db, start_date, end_date)

            # Proposal 분석
            proposal_metrics = await self._analyze_proposals(db, start_date, end_date)

            # Crawler 분석
            crawler_metrics = await self._analyze_crawlers(db, start_date, end_date)

            # Cost 분석
            cost_metrics = await self._analyze_costs(db, start_date, end_date)

        return {
            "insight_metrics": insight_metrics,
            "proposal_metrics": proposal_metrics,
            "crawler_metrics": crawler_metrics,
            "cost_metrics": cost_metrics,
        }

    async def _analyze_insights(
        self,
        db: aiosqlite.Connection,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> dict[str, Any]:
        """Insight confidence 분석"""
        query = """
            SELECT
                i.confidence,
                i.status,
                CASE WHEN p.response = 'ACCEPTED' THEN 1 ELSE 0 END as accepted
            FROM insights i
            LEFT JOIN proposals p ON i.id = p.insight_id
            WHERE 1=1
        """
        params = []

        if start_date:
            query += " AND i.created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND i.created_at <= ?"
            params.append(end_date)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        if not rows:
            return {"error": "No insights found"}

        # Confidence 분포
        confidences = [row["confidence"] for row in rows]
        accepted = [row["accepted"] for row in rows if row["accepted"] is not None]

        # Precision/Recall 계산 (multiple thresholds)
        thresholds = [round(x * 0.05, 2) for x in range(0, 21)]  # 0.0~1.0, step 0.05
        precision_recall = []

        for threshold in thresholds:
            tp = sum(1 for row in rows if row["confidence"] >= threshold and row["accepted"] == 1)
            fp = sum(1 for row in rows if row["confidence"] >= threshold and row["accepted"] == 0)
            fn = sum(1 for row in rows if row["confidence"] < threshold and row["accepted"] == 1)

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )

            precision_recall.append(
                {
                    "threshold": threshold,
                    "precision": round(precision, 3),
                    "recall": round(recall, 3),
                    "f1": round(f1, 3),
                }
            )

        # Best threshold (최대 F1)
        best = max(precision_recall, key=lambda x: x["f1"])

        return {
            "total_insights": len(rows),
            "accepted_count": sum(accepted),
            "acceptance_rate": round(sum(accepted) / len(accepted), 3) if accepted else 0.0,
            "avg_confidence": round(sum(confidences) / len(confidences), 3),
            "min_confidence": round(min(confidences), 3),
            "max_confidence": round(max(confidences), 3),
            "precision_recall_curve": precision_recall,
            "best_threshold": best,
        }

    async def _analyze_proposals(
        self,
        db: aiosqlite.Connection,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> dict[str, Any]:
        """Proposal 응답 분석"""
        query = """
            SELECT
                response,
                response_latency_sec,
                response_detail,
                proposed_at,
                response_at
            FROM proposals
            WHERE 1=1
        """
        params = []

        if start_date:
            query += " AND proposed_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND proposed_at <= ?"
            params.append(end_date)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        if not rows:
            return {"error": "No proposals found"}

        # Response 분포
        response_counts = defaultdict(int)
        for row in rows:
            response_counts[row["response"]] += 1

        # Latency 분석
        latencies = [
            row["response_latency_sec"]
            for row in rows
            if row["response_latency_sec"] is not None
        ]

        # Rejection reasons
        rejection_reasons = defaultdict(int)
        for row in rows:
            if row["response"] == "REJECTED" and row["response_detail"]:
                rejection_reasons[row["response_detail"]] += 1

        return {
            "total_proposals": len(rows),
            "response_counts": dict(response_counts),
            "acceptance_rate": round(
                response_counts["ACCEPTED"] / len(rows), 3
            ) if len(rows) > 0 else 0.0,
            "avg_response_latency_sec": (
                round(sum(latencies) / len(latencies), 1) if latencies else 0.0
            ),
            "median_response_latency_sec": (
                self._median(latencies) if latencies else 0.0
            ),
            "top_rejection_reasons": sorted(
                rejection_reasons.items(), key=lambda x: x[1], reverse=True
            )[:5],
        }

    async def _analyze_crawlers(
        self,
        db: aiosqlite.Connection,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> dict[str, Any]:
        """Crawler 성공/실패 패턴 분석"""
        query = """
            SELECT
                type,
                status,
                created_at,
                started_at,
                completed_at,
                last_error,
                attempts
            FROM jobs
            WHERE type = 'WATCH'
        """
        params = []

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()

        if not rows:
            return {"error": "No crawler jobs found"}

        # Status 분포
        status_counts = defaultdict(int)
        for row in rows:
            status_counts[row["status"]] += 1

        # 연속 실패 패턴
        failure_streaks = []
        current_streak = 0
        for row in rows:
            if row["status"] == "FAILED":
                current_streak += 1
            else:
                if current_streak > 0:
                    failure_streaks.append(current_streak)
                current_streak = 0

        # 재시도 분석
        retries = [row["attempts"] for row in rows if row["attempts"] > 1]

        return {
            "total_jobs": len(rows),
            "status_counts": dict(status_counts),
            "success_rate": round(
                status_counts["COMPLETED"] / len(rows), 3
            ) if len(rows) > 0 else 0.0,
            "avg_attempts": (
                round(sum(retries) / len(retries), 2) if retries else 1.0
            ),
            "max_failure_streak": max(failure_streaks) if failure_streaks else 0,
            "avg_failure_streak": (
                round(sum(failure_streaks) / len(failure_streaks), 2)
                if failure_streaks
                else 0.0
            ),
        }

    async def _analyze_costs(
        self,
        db: aiosqlite.Connection,
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> dict[str, Any]:
        """비용 분석"""
        query = """
            SELECT
                SUM(cost_usd) as total_cost_usd,
                SUM(tokens_in) as total_tokens_in,
                SUM(tokens_out) as total_tokens_out,
                COUNT(*) as total_calls
            FROM llm_calls
            WHERE 1=1
        """
        params = []

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date)
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date)

        cursor = await db.execute(query, params)
        row = await cursor.fetchone()

        total_cost_usd = row["total_cost_usd"] if row and row["total_cost_usd"] else 0.0
        total_tokens = (row["total_tokens_in"] or 0) + (row["total_tokens_out"] or 0)

        # Stage별 비용
        cursor = await db.execute(
            """
            SELECT stage, SUM(cost_usd) as cost
            FROM llm_calls
            WHERE 1=1
            GROUP BY stage
            """,
        )
        stage_costs = {row["stage"]: row["cost"] for row in await cursor.fetchall()}

        return {
            "total_cost_usd": round(total_cost_usd, 4),
            "total_calls": row["total_calls"] if row else 0,
            "total_tokens": total_tokens,
            "avg_cost_per_call": (
                round(total_cost_usd / row["total_calls"], 4)
                if row and row["total_calls"] > 0
                else 0.0
            ),
            "by_stage": {k: round(v, 4) for k, v in stage_costs.items()},
        }

    def calculate_optimal_threshold(
        self, precision_recall_curve: list[dict[str, Any]], strategy: str = "f1"
    ) -> float:
        """
        최적 threshold 계산

        Args:
            precision_recall_curve: [{"threshold": 0.7, "precision": 0.8, "recall": 0.9, "f1": 0.85}, ...]
            strategy: "f1" | "precision" | "recall" | "balanced"

        Returns:
            최적 threshold
        """
        if not precision_recall_curve:
            return 0.7  # Default

        if strategy == "f1":
            best = max(precision_recall_curve, key=lambda x: x["f1"])
            return best["threshold"]

        elif strategy == "precision":
            # Precision >= 0.8 중 최대 recall
            candidates = [p for p in precision_recall_curve if p["precision"] >= 0.8]
            if not candidates:
                candidates = precision_recall_curve
            best = max(candidates, key=lambda x: x["recall"])
            return best["threshold"]

        elif strategy == "recall":
            # Recall >= 0.8 중 최대 precision
            candidates = [p for p in precision_recall_curve if p["recall"] >= 0.8]
            if not candidates:
                candidates = precision_recall_curve
            best = max(candidates, key=lambda x: x["precision"])
            return best["threshold"]

        elif strategy == "balanced":
            # Precision과 Recall 차이 최소화
            best = min(
                precision_recall_curve,
                key=lambda x: abs(x["precision"] - x["recall"]),
            )
            return best["threshold"]

        else:
            return 0.7  # Default

    async def update_thresholds(
        self, adjustments: dict[str, Any], reason: str = "Optimizer"
    ) -> None:
        """
        thresholds.yaml 업데이트

        Args:
            adjustments: {"insight.confidence_threshold": 0.75, ...}
            reason: 조정 이유
        """
        config_path = Path(self.config_path)
        if not config_path.exists():
            logger.error(f"Config file not found: {config_path}")
            return

        # Load current config
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Apply adjustments
        changes = []
        for key, new_value in adjustments.items():
            parts = key.split(".")
            current = config
            for part in parts[:-1]:
                current = current.get(part, {})

            old_value = current.get(parts[-1])
            if old_value != new_value:
                current[parts[-1]] = new_value
                changes.append(f"{key}: {old_value} -> {new_value}")

        if not changes:
            logger.info("No changes to apply")
            return

        # Write back
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        # Log adjustment
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "changes": changes,
        }

        log_path = Path(config.get("auto_adjustments", {}).get("log_file", "data/auto_adjustments.log"))
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(yaml.dump([log_entry], allow_unicode=True))

        logger.info(f"Thresholds updated: {', '.join(changes)}")

    async def run_ab_test(
        self,
        control_threshold: float,
        test_threshold: float,
        sample_size: int = 50,
    ) -> dict[str, Any]:
        """
        A/B 테스트 시뮬레이션

        Args:
            control_threshold: 기준 threshold (e.g., 0.7)
            test_threshold: 테스트 threshold (e.g., 0.75)
            sample_size: 샘플 크기

        Returns:
            비교 결과
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Recent insights
            cursor = await db.execute(
                """
                SELECT
                    i.confidence,
                    CASE WHEN p.response = 'ACCEPTED' THEN 1 ELSE 0 END as accepted
                FROM insights i
                LEFT JOIN proposals p ON i.id = p.insight_id
                ORDER BY i.created_at DESC
                LIMIT ?
                """,
                (sample_size,),
            )
            rows = await cursor.fetchall()

        if not rows:
            return {"error": "Insufficient data"}

        # Control group
        control_pass = [row for row in rows if row["confidence"] >= control_threshold]
        control_tp = sum(1 for row in control_pass if row["accepted"] == 1)
        control_fp = sum(1 for row in control_pass if row["accepted"] == 0)

        # Test group
        test_pass = [row for row in rows if row["confidence"] >= test_threshold]
        test_tp = sum(1 for row in test_pass if row["accepted"] == 1)
        test_fp = sum(1 for row in test_pass if row["accepted"] == 0)

        control_precision = (
            control_tp / len(control_pass) if control_pass else 0.0
        )
        test_precision = test_tp / len(test_pass) if test_pass else 0.0

        return {
            "control": {
                "threshold": control_threshold,
                "passed": len(control_pass),
                "true_positives": control_tp,
                "false_positives": control_fp,
                "precision": round(control_precision, 3),
            },
            "test": {
                "threshold": test_threshold,
                "passed": len(test_pass),
                "true_positives": test_tp,
                "false_positives": test_fp,
                "precision": round(test_precision, 3),
            },
            "improvement": {
                "precision_delta": round(test_precision - control_precision, 3),
                "volume_delta": len(test_pass) - len(control_pass),
            },
        }

    @staticmethod
    def _median(values: list[float]) -> float:
        """Calculate median"""
        sorted_values = sorted(values)
        n = len(sorted_values)
        if n % 2 == 0:
            return (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2
        else:
            return sorted_values[n // 2]
