"""
Metrics API - Prometheus format export
14개 핵심 메트릭 (비용/품질/성능/시스템)

GET /metrics - Prometheus format
GET /metrics/json - JSON format
GET /metrics/grafana - Grafana dashboard template
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    메트릭 수집 및 Prometheus 포맷 변환

    14개 핵심 메트릭:
    [비용]
    1. sanjai_insight_cost_total_usd - 총 비용 (USD)
    2. sanjai_insight_cost_24h_usd - 24시간 비용 (USD)
    3. sanjai_insight_cost_per_insight_usd - 인사이트당 비용 (USD)

    [품질]
    4. sanjai_insight_acceptance_rate - 승인율
    5. sanjai_insight_confidence_avg - 평균 신뢰도
    6. sanjai_insight_high_confidence_ratio - 고신뢰도 비율 (>=0.8)

    [성능]
    7. sanjai_insight_insights_total - 총 인사이트 수
    8. sanjai_insight_insights_24h - 24시간 인사이트 수
    9. sanjai_insight_response_latency_avg_sec - 평균 응답 시간 (초)

    [시스템]
    10. sanjai_insight_jobs_pending - 대기 중 작업 수
    11. sanjai_insight_jobs_running - 실행 중 작업 수
    12. sanjai_insight_crawler_success_rate - 크롤러 성공률
    13. sanjai_insight_db_size_mb - DB 크기 (MB)
    14. sanjai_insight_uptime_seconds - 가동 시간 (초)
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.start_time = datetime.now()

    async def collect_metrics(self) -> dict[str, Any]:
        """
        모든 메트릭 수집

        Returns:
            {"metric_name": value, ...}
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            metrics = {}

            # === Cost Metrics ===
            # 1. Total cost
            cursor = await db.execute("SELECT SUM(cost_usd) as total FROM llm_calls")
            row = await cursor.fetchone()
            metrics["sanjai_insight_cost_total_usd"] = (
                row["total"] if row and row["total"] else 0.0
            )

            # 2. 24h cost
            cursor = await db.execute(
                """
                SELECT SUM(cost_usd) as total FROM llm_calls
                WHERE created_at >= datetime('now', '-24 hours')
                """
            )
            row = await cursor.fetchone()
            metrics["sanjai_insight_cost_24h_usd"] = (
                row["total"] if row and row["total"] else 0.0
            )

            # 3. Cost per insight
            cursor = await db.execute("SELECT COUNT(*) as cnt FROM insights")
            row = await cursor.fetchone()
            insight_count = row["cnt"] if row else 0
            metrics["sanjai_insight_cost_per_insight_usd"] = (
                metrics["sanjai_insight_cost_total_usd"] / insight_count
                if insight_count > 0
                else 0.0
            )

            # === Quality Metrics ===
            # 4. Acceptance rate
            cursor = await db.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN response = 'ACCEPTED' THEN 1 ELSE 0 END) as accepted
                FROM proposals
                WHERE response != 'PENDING'
                """
            )
            row = await cursor.fetchone()
            total_proposals = row["total"] if row else 0
            accepted = row["accepted"] if row and row["accepted"] else 0
            metrics["sanjai_insight_acceptance_rate"] = (
                accepted / total_proposals if total_proposals > 0 else 0.0
            )

            # 5. Average confidence
            cursor = await db.execute(
                "SELECT AVG(confidence) as avg FROM insights"
            )
            row = await cursor.fetchone()
            metrics["sanjai_insight_confidence_avg"] = (
                row["avg"] if row and row["avg"] else 0.0
            )

            # 6. High confidence ratio
            cursor = await db.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN confidence >= 0.8 THEN 1 ELSE 0 END) as high
                FROM insights
                """
            )
            row = await cursor.fetchone()
            total_insights = row["total"] if row else 0
            high_confidence = row["high"] if row and row["high"] else 0
            metrics["sanjai_insight_high_confidence_ratio"] = (
                high_confidence / total_insights if total_insights > 0 else 0.0
            )

            # === Performance Metrics ===
            # 7. Total insights
            metrics["sanjai_insight_insights_total"] = insight_count

            # 8. 24h insights
            cursor = await db.execute(
                """
                SELECT COUNT(*) as cnt FROM insights
                WHERE created_at >= datetime('now', '-24 hours')
                """
            )
            row = await cursor.fetchone()
            metrics["sanjai_insight_insights_24h"] = row["cnt"] if row else 0

            # 9. Average response latency
            cursor = await db.execute(
                """
                SELECT AVG(response_latency_sec) as avg FROM proposals
                WHERE response_latency_sec IS NOT NULL
                """
            )
            row = await cursor.fetchone()
            metrics["sanjai_insight_response_latency_avg_sec"] = (
                row["avg"] if row and row["avg"] else 0.0
            )

            # === System Metrics ===
            # 10. Pending jobs
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM jobs WHERE status = 'PENDING'"
            )
            row = await cursor.fetchone()
            metrics["sanjai_insight_jobs_pending"] = row["cnt"] if row else 0

            # 11. Running jobs
            cursor = await db.execute(
                "SELECT COUNT(*) as cnt FROM jobs WHERE status = 'RUNNING'"
            )
            row = await cursor.fetchone()
            metrics["sanjai_insight_jobs_running"] = row["cnt"] if row else 0

            # 12. Crawler success rate
            cursor = await db.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as success
                FROM jobs
                WHERE type = 'WATCH'
                """
            )
            row = await cursor.fetchone()
            total_crawler_jobs = row["total"] if row else 0
            success_crawler_jobs = row["success"] if row and row["success"] else 0
            metrics["sanjai_insight_crawler_success_rate"] = (
                success_crawler_jobs / total_crawler_jobs
                if total_crawler_jobs > 0
                else 0.0
            )

            # 13. DB size
            cursor = await db.execute("PRAGMA page_count")
            page_count = (await cursor.fetchone())[0]
            cursor = await db.execute("PRAGMA page_size")
            page_size = (await cursor.fetchone())[0]
            db_size_bytes = page_count * page_size
            metrics["sanjai_insight_db_size_mb"] = db_size_bytes / (1024 * 1024)

            # 14. Uptime
            uptime_seconds = (datetime.now() - self.start_time).total_seconds()
            metrics["sanjai_insight_uptime_seconds"] = uptime_seconds

        return metrics

    def format_prometheus(self, metrics: dict[str, Any]) -> str:
        """
        Prometheus format으로 변환

        Returns:
            # HELP ...
            # TYPE ...
            metric_name value
        """
        output = []

        # Metric definitions
        definitions = {
            "sanjai_insight_cost_total_usd": ("Total cost in USD", "counter"),
            "sanjai_insight_cost_24h_usd": ("24h cost in USD", "gauge"),
            "sanjai_insight_cost_per_insight_usd": (
                "Cost per insight in USD",
                "gauge",
            ),
            "sanjai_insight_acceptance_rate": ("Proposal acceptance rate", "gauge"),
            "sanjai_insight_confidence_avg": ("Average confidence score", "gauge"),
            "sanjai_insight_high_confidence_ratio": (
                "High confidence ratio (>=0.8)",
                "gauge",
            ),
            "sanjai_insight_insights_total": ("Total insights generated", "counter"),
            "sanjai_insight_insights_24h": ("Insights in last 24h", "gauge"),
            "sanjai_insight_response_latency_avg_sec": (
                "Average response latency in seconds",
                "gauge",
            ),
            "sanjai_insight_jobs_pending": ("Pending jobs", "gauge"),
            "sanjai_insight_jobs_running": ("Running jobs", "gauge"),
            "sanjai_insight_crawler_success_rate": ("Crawler success rate", "gauge"),
            "sanjai_insight_db_size_mb": ("Database size in MB", "gauge"),
            "sanjai_insight_uptime_seconds": ("Uptime in seconds", "counter"),
        }

        for metric_name, value in metrics.items():
            if metric_name in definitions:
                help_text, metric_type = definitions[metric_name]
                output.append(f"# HELP {metric_name} {help_text}")
                output.append(f"# TYPE {metric_name} {metric_type}")
                output.append(f"{metric_name} {value}")
                output.append("")

        return "\n".join(output)

    async def get_prometheus_metrics(self) -> str:
        """Prometheus format 메트릭 반환"""
        metrics = await self.collect_metrics()
        return self.format_prometheus(metrics)

    async def get_json_metrics(self) -> dict[str, Any]:
        """JSON format 메트릭 반환"""
        metrics = await self.collect_metrics()
        return {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
        }

    async def get_grafana_dashboard(self) -> dict[str, Any]:
        """
        Grafana dashboard JSON template 반환

        Returns:
            Grafana dashboard JSON
        """
        dashboard = {
            "dashboard": {
                "title": "sanjai-insight Metrics",
                "tags": ["sanjai", "insight"],
                "timezone": "browser",
                "panels": [
                    # Row 1: Cost Metrics
                    {
                        "id": 1,
                        "title": "Total Cost (USD)",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "sanjai_insight_cost_total_usd",
                                "legendFormat": "Total Cost",
                            }
                        ],
                        "gridPos": {"x": 0, "y": 0, "w": 6, "h": 4},
                    },
                    {
                        "id": 2,
                        "title": "24h Cost (USD)",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "sanjai_insight_cost_24h_usd",
                                "legendFormat": "24h Cost",
                            }
                        ],
                        "gridPos": {"x": 6, "y": 0, "w": 6, "h": 4},
                    },
                    {
                        "id": 3,
                        "title": "Cost per Insight (USD)",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "sanjai_insight_cost_per_insight_usd",
                                "legendFormat": "Per Insight",
                            }
                        ],
                        "gridPos": {"x": 12, "y": 0, "w": 6, "h": 4},
                    },
                    # Row 2: Quality Metrics
                    {
                        "id": 4,
                        "title": "Acceptance Rate",
                        "type": "gauge",
                        "targets": [
                            {
                                "expr": "sanjai_insight_acceptance_rate",
                                "legendFormat": "Acceptance Rate",
                            }
                        ],
                        "gridPos": {"x": 0, "y": 4, "w": 6, "h": 6},
                        "fieldConfig": {
                            "defaults": {"min": 0, "max": 1, "unit": "percentunit"}
                        },
                    },
                    {
                        "id": 5,
                        "title": "Average Confidence",
                        "type": "gauge",
                        "targets": [
                            {
                                "expr": "sanjai_insight_confidence_avg",
                                "legendFormat": "Avg Confidence",
                            }
                        ],
                        "gridPos": {"x": 6, "y": 4, "w": 6, "h": 6},
                        "fieldConfig": {
                            "defaults": {"min": 0, "max": 1, "unit": "percentunit"}
                        },
                    },
                    {
                        "id": 6,
                        "title": "High Confidence Ratio",
                        "type": "gauge",
                        "targets": [
                            {
                                "expr": "sanjai_insight_high_confidence_ratio",
                                "legendFormat": "High Confidence",
                            }
                        ],
                        "gridPos": {"x": 12, "y": 4, "w": 6, "h": 6},
                        "fieldConfig": {
                            "defaults": {"min": 0, "max": 1, "unit": "percentunit"}
                        },
                    },
                    # Row 3: Performance Metrics
                    {
                        "id": 7,
                        "title": "Total Insights",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "sanjai_insight_insights_total",
                                "legendFormat": "Total",
                            }
                        ],
                        "gridPos": {"x": 0, "y": 10, "w": 6, "h": 4},
                    },
                    {
                        "id": 8,
                        "title": "24h Insights",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "sanjai_insight_insights_24h",
                                "legendFormat": "24h",
                            }
                        ],
                        "gridPos": {"x": 6, "y": 10, "w": 6, "h": 4},
                    },
                    {
                        "id": 9,
                        "title": "Response Latency (sec)",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "sanjai_insight_response_latency_avg_sec",
                                "legendFormat": "Avg Latency",
                            }
                        ],
                        "gridPos": {"x": 12, "y": 10, "w": 12, "h": 6},
                    },
                    # Row 4: System Metrics
                    {
                        "id": 10,
                        "title": "Jobs Status",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "sanjai_insight_jobs_pending",
                                "legendFormat": "Pending",
                            },
                            {
                                "expr": "sanjai_insight_jobs_running",
                                "legendFormat": "Running",
                            },
                        ],
                        "gridPos": {"x": 0, "y": 14, "w": 6, "h": 4},
                    },
                    {
                        "id": 11,
                        "title": "Crawler Success Rate",
                        "type": "gauge",
                        "targets": [
                            {
                                "expr": "sanjai_insight_crawler_success_rate",
                                "legendFormat": "Success Rate",
                            }
                        ],
                        "gridPos": {"x": 6, "y": 14, "w": 6, "h": 6},
                        "fieldConfig": {
                            "defaults": {"min": 0, "max": 1, "unit": "percentunit"}
                        },
                    },
                    {
                        "id": 12,
                        "title": "DB Size (MB)",
                        "type": "graph",
                        "targets": [
                            {
                                "expr": "sanjai_insight_db_size_mb",
                                "legendFormat": "DB Size",
                            }
                        ],
                        "gridPos": {"x": 12, "y": 14, "w": 6, "h": 6},
                    },
                    {
                        "id": 13,
                        "title": "Uptime (hours)",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "sanjai_insight_uptime_seconds / 3600",
                                "legendFormat": "Uptime",
                            }
                        ],
                        "gridPos": {"x": 18, "y": 14, "w": 6, "h": 4},
                    },
                ],
                "refresh": "30s",
                "schemaVersion": 27,
                "version": 1,
            }
        }

        return dashboard
