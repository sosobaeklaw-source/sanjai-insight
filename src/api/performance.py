"""
Performance API Endpoints
Real-time performance monitoring dashboard

Endpoints:
    GET /metrics/performance/summary - Overall performance summary
    GET /metrics/performance/latency - Detailed latency analysis
    GET /metrics/performance/throughput - Throughput analysis
    GET /metrics/performance/bottlenecks - Bottleneck identification
"""

import logging
from typing import Any, Dict

from ..metrics.performance_tracker import PerformanceTracker

logger = logging.getLogger(__name__)


async def get_performance_summary(db_path: str) -> Dict[str, Any]:
    """
    Get overall performance summary

    Returns:
        {
            "timestamp": "2026-03-04T...",
            "latency": {
                "avg_p95_ms": 1234.5,
                "endpoint_count": 10
            },
            "throughput": {
                "total_rps": 12.5,
                "avg_success_rate": 0.98
            },
            "resources": {...},
            "bottlenecks": [...],
            "health": "healthy" | "degraded"
        }
    """
    try:
        tracker = PerformanceTracker(db_path=db_path)
        summary = await tracker.get_performance_summary()
        return summary
    except Exception as e:
        logger.error(f"Error getting performance summary: {e}")
        return {
            "error": str(e),
            "health": "unknown",
        }


async def get_latency_analysis(db_path: str) -> Dict[str, Any]:
    """
    Get detailed latency analysis

    Returns:
        {
            "timestamp": "2026-03-04T...",
            "window_minutes": 15,
            "endpoints": {
                "api:endpoint1": {
                    "p50": 100,
                    "p95": 500,
                    "p99": 1000,
                    "mean": 200,
                    "min": 50,
                    "max": 2000,
                    "count": 1000
                },
                ...
            }
        }
    """
    try:
        tracker = PerformanceTracker(db_path=db_path)
        analysis = await tracker.get_latency_analysis()
        return analysis
    except Exception as e:
        logger.error(f"Error getting latency analysis: {e}")
        return {
            "error": str(e),
            "endpoints": {},
        }


async def get_throughput_analysis(db_path: str) -> Dict[str, Any]:
    """
    Get detailed throughput analysis

    Returns:
        {
            "timestamp": "2026-03-04T...",
            "window_minutes": 15,
            "components": {
                "api": {
                    "rps": 12.5,
                    "total_requests": 11250,
                    "success_rate": 0.98,
                    "error_rate": 0.02,
                    "success_count": 11025,
                    "error_count": 225
                },
                ...
            }
        }
    """
    try:
        tracker = PerformanceTracker(db_path=db_path)
        analysis = await tracker.get_throughput_analysis()
        return analysis
    except Exception as e:
        logger.error(f"Error getting throughput analysis: {e}")
        return {
            "error": str(e),
            "components": {},
        }


async def get_bottlenecks_analysis(db_path: str) -> Dict[str, Any]:
    """
    Get detailed bottleneck analysis

    Returns:
        {
            "timestamp": "2026-03-04T...",
            "bottlenecks": [
                {
                    "type": "endpoint",
                    "component": "api",
                    "description": "Slow endpoint: api:search (P95: 5123ms)",
                    "severity": "HIGH",
                    "metrics": {...},
                    "timestamp": "2026-03-04T..."
                },
                ...
            ],
            "slow_queries": [
                {
                    "query": "SELECT ...",
                    "avg_duration_ms": 1234.5,
                    "max_duration_ms": 3000.0,
                    "execution_count": 123
                },
                ...
            ]
        }
    """
    try:
        tracker = PerformanceTracker(db_path=db_path)
        analysis = await tracker.get_bottlenecks_analysis()
        return analysis
    except Exception as e:
        logger.error(f"Error getting bottleneck analysis: {e}")
        return {
            "error": str(e),
            "bottlenecks": [],
            "slow_queries": [],
        }


async def get_performance_alerts(db_path: str) -> Dict[str, Any]:
    """
    Check performance alerts

    Returns:
        {
            "timestamp": "2026-03-04T...",
            "alerts": [
                {
                    "id": "uuid",
                    "metric": "p95_latency_ms",
                    "threshold": 5000,
                    "current_value": 6234.5,
                    "comparison": ">",
                    "timestamp": "2026-03-04T...",
                    "severity": "HIGH"
                },
                ...
            ]
        }
    """
    try:
        tracker = PerformanceTracker(db_path=db_path)
        alerts = await tracker.check_alerts()
        return {
            "timestamp": None,  # Will be added by tracker
            "alerts": alerts,
        }
    except Exception as e:
        logger.error(f"Error checking performance alerts: {e}")
        return {
            "error": str(e),
            "alerts": [],
        }
