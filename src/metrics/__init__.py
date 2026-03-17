"""
Metrics module for sanjai-insight.

Components:
- performance_tracker: Real-time performance monitoring and analysis
"""

try:
    from .performance_tracker import (
        PerformanceTracker,
        set_global_tracker,
        track_latency,
        track_performance,
    )
except ImportError:  # pragma: no cover - optional metrics dependency
    PerformanceTracker = None
    set_global_tracker = None
    track_latency = None
    track_performance = None

__all__ = [
    "PerformanceTracker",
    "set_global_tracker",
    "track_latency",
    "track_performance",
]
