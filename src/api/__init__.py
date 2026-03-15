"""
sanjai-insight API Endpoints
"""

from .health import get_health, get_healthz
from .cost import get_cost
from .status import get_status

try:
    from .performance import (
        get_performance_summary,
        get_latency_analysis,
        get_throughput_analysis,
        get_bottlenecks_analysis,
        get_performance_alerts,
    )
except ImportError:  # pragma: no cover - optional metrics dependency
    get_performance_summary = None
    get_latency_analysis = None
    get_throughput_analysis = None
    get_bottlenecks_analysis = None
    get_performance_alerts = None

__all__ = [
    "get_healthz",
    "get_health",
    "get_status",
    "get_cost",
    "get_performance_summary",
    "get_latency_analysis",
    "get_throughput_analysis",
    "get_bottlenecks_analysis",
    "get_performance_alerts",
]
