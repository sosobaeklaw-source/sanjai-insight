"""
Performance Tracker System
Comprehensive real-time performance monitoring and analysis.

Tracks:
- API endpoint latency (P50, P95, P99)
- Throughput (RPS, success/error rates)
- Resource usage (CPU, memory, disk I/O, DB connections)
- Bottleneck identification (slow queries, slow endpoints)
- Alert thresholds (P95 > 5s, error rate > 5%, CPU > 80%, memory > 90%)

Usage:
    tracker = PerformanceTracker("data/insight.db")

    # Decorator usage
    @track_performance
    async def my_function():
        pass

    @track_latency("api_endpoint")
    async def handle_request():
        pass

    # Dashboard API
    GET /metrics/performance/summary
    GET /metrics/performance/latency
    GET /metrics/performance/throughput
    GET /metrics/performance/bottlenecks
"""

import asyncio
import functools
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple
from uuid import uuid4

import aiosqlite

try:
    import psutil
except ImportError:  # pragma: no cover - optional metrics dependency
    psutil = None

logger = logging.getLogger(__name__)


# ========== Data Classes ==========


@dataclass
class LatencyMetric:
    """Latency measurement"""
    timestamp: datetime
    component: str
    endpoint: str
    latency_ms: float
    success: bool
    error_type: Optional[str] = None


@dataclass
class ThroughputMetric:
    """Throughput measurement"""
    timestamp: datetime
    component: str
    requests_count: int
    success_count: int
    error_count: int
    window_seconds: int


@dataclass
class ResourceMetric:
    """Resource usage measurement"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    disk_read_mb: float
    disk_write_mb: float
    db_connections: int


@dataclass
class BottleneckInfo:
    """Bottleneck identification"""
    type: str  # "query", "endpoint", "resource", "memory_leak"
    component: str
    description: str
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    metrics: Dict[str, Any]
    timestamp: datetime


@dataclass
class PercentileStats:
    """Percentile statistics"""
    p50: float
    p95: float
    p99: float
    mean: float
    min: float
    max: float
    count: int


@dataclass
class AlertThreshold:
    """Alert threshold configuration"""
    metric_name: str
    threshold: float
    comparison: str  # ">", "<", ">=", "<=", "=="
    window_seconds: int = 300  # 5 minutes default


# ========== Performance Tracker ==========


class PerformanceTracker:
    """
    Real-time performance tracking and analysis system.

    Features:
    - Latency tracking with percentiles (P50, P95, P99)
    - Throughput tracking (RPS, success/error rates)
    - Resource monitoring (CPU, memory, disk, DB)
    - Bottleneck detection (slow queries, slow endpoints)
    - Alert system with configurable thresholds
    """

    def __init__(
        self,
        db_path: str = "data/insight.db",
        window_size: int = 1000,
        history_hours: int = 24,
    ):
        self.db_path = db_path
        self.window_size = window_size
        self.history_hours = history_hours

        # In-memory circular buffers for real-time metrics
        self.latency_buffer: Deque[LatencyMetric] = deque(maxlen=window_size)
        self.throughput_buffer: Deque[ThroughputMetric] = deque(maxlen=window_size)
        self.resource_buffer: Deque[ResourceMetric] = deque(maxlen=window_size)

        # Per-endpoint tracking
        self.endpoint_latencies: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=window_size)
        )
        self.endpoint_errors: Dict[str, int] = defaultdict(int)
        self.endpoint_requests: Dict[str, int] = defaultdict(int)

        # Resource tracking
        self.process = psutil.Process(os.getpid()) if psutil is not None else None
        self.disk_io_prev = self.process.io_counters() if self.process is not None else None
        self.last_resource_check = time.time()

        # Alert thresholds
        self.alert_thresholds = self._init_alert_thresholds()
        self.alert_cooldown: Dict[str, datetime] = {}

        # Background tasks
        self._resource_monitor_task: Optional[asyncio.Task] = None
        self._db_persist_task: Optional[asyncio.Task] = None

    def _init_alert_thresholds(self) -> List[AlertThreshold]:
        """Initialize default alert thresholds"""
        return [
            AlertThreshold("p95_latency_ms", 5000.0, ">", 300),
            AlertThreshold("error_rate", 0.05, ">", 300),
            AlertThreshold("cpu_percent", 80.0, ">", 300),
            AlertThreshold("memory_percent", 90.0, ">", 300),
            AlertThreshold("db_connections", 50, ">", 300),
        ]

    async def start(self):
        """Start background monitoring tasks"""
        self._resource_monitor_task = asyncio.create_task(self._monitor_resources())
        self._db_persist_task = asyncio.create_task(self._persist_metrics())
        logger.info("PerformanceTracker started")

    async def stop(self):
        """Stop background monitoring tasks"""
        if self._resource_monitor_task:
            self._resource_monitor_task.cancel()
            try:
                await self._resource_monitor_task
            except asyncio.CancelledError:
                pass

        if self._db_persist_task:
            self._db_persist_task.cancel()
            try:
                await self._db_persist_task
            except asyncio.CancelledError:
                pass

        logger.info("PerformanceTracker stopped")

    # ========== Tracking Methods ==========

    def track_latency(
        self,
        component: str,
        endpoint: str,
        latency_ms: float,
        success: bool = True,
        error_type: Optional[str] = None,
    ):
        """Track latency measurement"""
        metric = LatencyMetric(
            timestamp=datetime.now(),
            component=component,
            endpoint=endpoint,
            latency_ms=latency_ms,
            success=success,
            error_type=error_type,
        )

        self.latency_buffer.append(metric)
        self.endpoint_latencies[f"{component}:{endpoint}"].append(latency_ms)
        self.endpoint_requests[f"{component}:{endpoint}"] += 1

        if not success:
            self.endpoint_errors[f"{component}:{endpoint}"] += 1

    def track_throughput(
        self,
        component: str,
        requests_count: int,
        success_count: int,
        error_count: int,
        window_seconds: int = 60,
    ):
        """Track throughput measurement"""
        metric = ThroughputMetric(
            timestamp=datetime.now(),
            component=component,
            requests_count=requests_count,
            success_count=success_count,
            error_count=error_count,
            window_seconds=window_seconds,
        )

        self.throughput_buffer.append(metric)

    def track_resource_usage(self):
        """Track current resource usage"""
        try:
            if self.process is None:
                metric = ResourceMetric(
                    timestamp=datetime.now(),
                    cpu_percent=0.0,
                    memory_percent=0.0,
                    memory_mb=0.0,
                    disk_read_mb=0.0,
                    disk_write_mb=0.0,
                    db_connections=0,
                )
                self.resource_buffer.append(metric)
                return

            # CPU and memory
            cpu_percent = self.process.cpu_percent()
            mem_info = self.process.memory_info()
            mem_percent = self.process.memory_percent()
            mem_mb = mem_info.rss / 1024 / 1024

            # Disk I/O
            disk_io = self.process.io_counters()
            time_delta = time.time() - self.last_resource_check

            if time_delta > 0:
                disk_read_mb = (disk_io.read_bytes - self.disk_io_prev.read_bytes) / 1024 / 1024
                disk_write_mb = (disk_io.write_bytes - self.disk_io_prev.write_bytes) / 1024 / 1024
            else:
                disk_read_mb = 0
                disk_write_mb = 0

            self.disk_io_prev = disk_io
            self.last_resource_check = time.time()

            # DB connections (approximate via open files)
            db_connections = len([f for f in self.process.open_files() if f.path.endswith(".db")])

            metric = ResourceMetric(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=mem_percent,
                memory_mb=mem_mb,
                disk_read_mb=disk_read_mb,
                disk_write_mb=disk_write_mb,
                db_connections=db_connections,
            )

            self.resource_buffer.append(metric)

        except Exception as e:
            logger.error(f"Error tracking resource usage: {e}")

    # ========== Analysis Methods ==========

    def calculate_percentiles(self, values: List[float]) -> PercentileStats:
        """Calculate percentile statistics"""
        if not values:
            return PercentileStats(0, 0, 0, 0, 0, 0, 0)

        sorted_values = sorted(values)
        count = len(sorted_values)

        def percentile(p: float) -> float:
            k = (count - 1) * p
            f = int(k)
            c = f + 1
            if c >= count:
                return sorted_values[-1]
            d0 = sorted_values[f] * (c - k)
            d1 = sorted_values[c] * (k - f)
            return d0 + d1

        return PercentileStats(
            p50=percentile(0.50),
            p95=percentile(0.95),
            p99=percentile(0.99),
            mean=sum(values) / count,
            min=sorted_values[0],
            max=sorted_values[-1],
            count=count,
        )

    def get_latency_stats(
        self,
        component: Optional[str] = None,
        endpoint: Optional[str] = None,
        minutes: int = 5,
    ) -> Dict[str, PercentileStats]:
        """Get latency statistics"""
        cutoff = datetime.now() - timedelta(minutes=minutes)

        # Filter metrics
        filtered = [
            m for m in self.latency_buffer
            if m.timestamp >= cutoff
            and (component is None or m.component == component)
            and (endpoint is None or m.endpoint == endpoint)
        ]

        # Group by endpoint
        by_endpoint: Dict[str, List[float]] = defaultdict(list)
        for m in filtered:
            key = f"{m.component}:{m.endpoint}"
            by_endpoint[key].append(m.latency_ms)

        # Calculate stats
        return {
            endpoint: self.calculate_percentiles(latencies)
            for endpoint, latencies in by_endpoint.items()
        }

    def get_throughput_stats(
        self,
        component: Optional[str] = None,
        minutes: int = 5,
    ) -> Dict[str, Dict[str, Any]]:
        """Get throughput statistics"""
        cutoff = datetime.now() - timedelta(minutes=minutes)

        # Filter metrics
        filtered = [
            m for m in self.throughput_buffer
            if m.timestamp >= cutoff
            and (component is None or m.component == component)
        ]

        # Aggregate by component
        by_component: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"requests": 0, "success": 0, "error": 0}
        )

        for m in filtered:
            by_component[m.component]["requests"] += m.requests_count
            by_component[m.component]["success"] += m.success_count
            by_component[m.component]["error"] += m.error_count

        # Calculate rates
        result = {}
        for comp, stats in by_component.items():
            total = stats["requests"]
            result[comp] = {
                "rps": total / (minutes * 60) if minutes > 0 else 0,
                "total_requests": total,
                "success_rate": stats["success"] / total if total > 0 else 0,
                "error_rate": stats["error"] / total if total > 0 else 0,
                "success_count": stats["success"],
                "error_count": stats["error"],
            }

        return result

    def get_resource_stats(self, minutes: int = 5) -> Dict[str, Any]:
        """Get resource usage statistics"""
        cutoff = datetime.now() - timedelta(minutes=minutes)

        filtered = [m for m in self.resource_buffer if m.timestamp >= cutoff]

        if not filtered:
            return {
                "cpu_percent": {"current": 0, "avg": 0, "max": 0},
                "memory_percent": {"current": 0, "avg": 0, "max": 0},
                "memory_mb": {"current": 0, "avg": 0, "max": 0},
                "disk_read_mb_per_sec": 0,
                "disk_write_mb_per_sec": 0,
                "db_connections": {"current": 0, "avg": 0, "max": 0},
            }

        cpu_values = [m.cpu_percent for m in filtered]
        mem_percent_values = [m.memory_percent for m in filtered]
        mem_mb_values = [m.memory_mb for m in filtered]
        db_conn_values = [m.db_connections for m in filtered]

        total_disk_read = sum(m.disk_read_mb for m in filtered)
        total_disk_write = sum(m.disk_write_mb for m in filtered)

        return {
            "cpu_percent": {
                "current": filtered[-1].cpu_percent,
                "avg": sum(cpu_values) / len(cpu_values),
                "max": max(cpu_values),
            },
            "memory_percent": {
                "current": filtered[-1].memory_percent,
                "avg": sum(mem_percent_values) / len(mem_percent_values),
                "max": max(mem_percent_values),
            },
            "memory_mb": {
                "current": filtered[-1].memory_mb,
                "avg": sum(mem_mb_values) / len(mem_mb_values),
                "max": max(mem_mb_values),
            },
            "disk_read_mb_per_sec": total_disk_read / (minutes * 60),
            "disk_write_mb_per_sec": total_disk_write / (minutes * 60),
            "db_connections": {
                "current": filtered[-1].db_connections,
                "avg": sum(db_conn_values) / len(db_conn_values),
                "max": max(db_conn_values),
            },
        }

    def identify_bottlenecks(self) -> List[BottleneckInfo]:
        """Identify performance bottlenecks"""
        bottlenecks = []
        now = datetime.now()

        # 1. Slow endpoints (P95 > 5s)
        latency_stats = self.get_latency_stats(minutes=5)
        for endpoint, stats in latency_stats.items():
            if stats.p95 > 5000:  # 5 seconds
                severity = "CRITICAL" if stats.p95 > 10000 else "HIGH"
                bottlenecks.append(
                    BottleneckInfo(
                        type="endpoint",
                        component=endpoint.split(":")[0],
                        description=f"Slow endpoint: {endpoint} (P95: {stats.p95:.0f}ms)",
                        severity=severity,
                        metrics={
                            "p95": stats.p95,
                            "p99": stats.p99,
                            "mean": stats.mean,
                        },
                        timestamp=now,
                    )
                )

        # 2. High error rate (> 5%)
        throughput_stats = self.get_throughput_stats(minutes=5)
        for component, stats in throughput_stats.items():
            if stats["error_rate"] > 0.05:  # 5%
                severity = "CRITICAL" if stats["error_rate"] > 0.20 else "HIGH"
                bottlenecks.append(
                    BottleneckInfo(
                        type="error_rate",
                        component=component,
                        description=f"High error rate: {component} ({stats['error_rate']*100:.1f}%)",
                        severity=severity,
                        metrics=stats,
                        timestamp=now,
                    )
                )

        # 3. Resource constraints
        resource_stats = self.get_resource_stats(minutes=5)

        if resource_stats["cpu_percent"]["current"] > 80:
            severity = "CRITICAL" if resource_stats["cpu_percent"]["current"] > 95 else "HIGH"
            bottlenecks.append(
                BottleneckInfo(
                    type="resource",
                    component="cpu",
                    description=f"High CPU usage: {resource_stats['cpu_percent']['current']:.1f}%",
                    severity=severity,
                    metrics=resource_stats["cpu_percent"],
                    timestamp=now,
                )
            )

        if resource_stats["memory_percent"]["current"] > 90:
            severity = "CRITICAL"
            bottlenecks.append(
                BottleneckInfo(
                    type="resource",
                    component="memory",
                    description=f"High memory usage: {resource_stats['memory_percent']['current']:.1f}%",
                    severity=severity,
                    metrics=resource_stats["memory_percent"],
                    timestamp=now,
                )
            )

        # 4. Memory leak detection (increasing trend)
        if len(self.resource_buffer) >= 10:
            recent = list(self.resource_buffer)[-10:]
            mem_trend = [m.memory_mb for m in recent]

            # Simple linear regression slope
            n = len(mem_trend)
            x_mean = (n - 1) / 2
            y_mean = sum(mem_trend) / n
            slope = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(mem_trend)) / \
                    sum((i - x_mean) ** 2 for i in range(n))

            # If memory is increasing by more than 1MB per measurement
            if slope > 1.0:
                bottlenecks.append(
                    BottleneckInfo(
                        type="memory_leak",
                        component="system",
                        description=f"Potential memory leak detected (slope: {slope:.2f} MB/sample)",
                        severity="MEDIUM",
                        metrics={
                            "slope": slope,
                            "current_mb": mem_trend[-1],
                            "start_mb": mem_trend[0],
                        },
                        timestamp=now,
                    )
                )

        return bottlenecks

    async def get_slow_queries_from_db(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get slow queries from database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row

                # Assuming we have a query log table
                cursor = await db.execute(
                    """
                    SELECT
                        query,
                        AVG(duration_ms) as avg_duration_ms,
                        MAX(duration_ms) as max_duration_ms,
                        COUNT(*) as execution_count
                    FROM query_log
                    WHERE timestamp >= datetime('now', '-1 hour')
                    GROUP BY query
                    ORDER BY avg_duration_ms DESC
                    LIMIT ?
                    """,
                    (limit,),
                )

                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Error fetching slow queries: {e}")
            return []

    # ========== Alert System ==========

    async def check_alerts(self) -> List[Dict[str, Any]]:
        """Check alert thresholds and return triggered alerts"""
        alerts = []
        now = datetime.now()

        # Get current metrics
        latency_stats = self.get_latency_stats(minutes=5)
        throughput_stats = self.get_throughput_stats(minutes=5)
        resource_stats = self.get_resource_stats(minutes=5)

        # Check thresholds
        for threshold in self.alert_thresholds:
            # Check cooldown
            if threshold.metric_name in self.alert_cooldown:
                if (now - self.alert_cooldown[threshold.metric_name]).total_seconds() < threshold.window_seconds:
                    continue

            triggered = False
            metric_value = None

            # Check specific metrics
            if threshold.metric_name == "p95_latency_ms":
                # Check any endpoint with high P95
                for endpoint, stats in latency_stats.items():
                    if self._compare_value(stats.p95, threshold.threshold, threshold.comparison):
                        triggered = True
                        metric_value = stats.p95
                        break

            elif threshold.metric_name == "error_rate":
                for component, stats in throughput_stats.items():
                    if self._compare_value(stats["error_rate"], threshold.threshold, threshold.comparison):
                        triggered = True
                        metric_value = stats["error_rate"]
                        break

            elif threshold.metric_name == "cpu_percent":
                current_cpu = resource_stats["cpu_percent"]["current"]
                if self._compare_value(current_cpu, threshold.threshold, threshold.comparison):
                    triggered = True
                    metric_value = current_cpu

            elif threshold.metric_name == "memory_percent":
                current_mem = resource_stats["memory_percent"]["current"]
                if self._compare_value(current_mem, threshold.threshold, threshold.comparison):
                    triggered = True
                    metric_value = current_mem

            elif threshold.metric_name == "db_connections":
                current_db = resource_stats["db_connections"]["current"]
                if self._compare_value(current_db, threshold.threshold, threshold.comparison):
                    triggered = True
                    metric_value = current_db

            if triggered:
                alert = {
                    "id": str(uuid4()),
                    "metric": threshold.metric_name,
                    "threshold": threshold.threshold,
                    "current_value": metric_value,
                    "comparison": threshold.comparison,
                    "timestamp": now.isoformat(),
                    "severity": self._get_alert_severity(threshold.metric_name, metric_value, threshold.threshold),
                }
                alerts.append(alert)
                self.alert_cooldown[threshold.metric_name] = now

        return alerts

    def _compare_value(self, value: float, threshold: float, comparison: str) -> bool:
        """Compare value against threshold"""
        if comparison == ">":
            return value > threshold
        elif comparison == "<":
            return value < threshold
        elif comparison == ">=":
            return value >= threshold
        elif comparison == "<=":
            return value <= threshold
        elif comparison == "==":
            return value == threshold
        return False

    def _get_alert_severity(self, metric: str, value: float, threshold: float) -> str:
        """Determine alert severity"""
        ratio = value / threshold if threshold > 0 else 1.0

        if ratio >= 2.0:
            return "CRITICAL"
        elif ratio >= 1.5:
            return "HIGH"
        elif ratio >= 1.2:
            return "MEDIUM"
        else:
            return "LOW"

    # ========== Background Tasks ==========

    async def _monitor_resources(self):
        """Background task to monitor resources"""
        while True:
            try:
                self.track_resource_usage()
                await asyncio.sleep(5)  # Every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in resource monitoring: {e}")
                await asyncio.sleep(5)

    async def _persist_metrics(self):
        """Background task to persist metrics to database"""
        while True:
            try:
                await asyncio.sleep(60)  # Every minute
                await self._save_metrics_to_db()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error persisting metrics: {e}")
                await asyncio.sleep(60)

    async def _save_metrics_to_db(self):
        """Save current metrics to database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # Aggregate recent metrics
                latency_stats = self.get_latency_stats(minutes=1)
                throughput_stats = self.get_throughput_stats(minutes=1)
                resource_stats = self.get_resource_stats(minutes=1)

                timestamp = datetime.now().isoformat()

                # Save latency metrics
                for endpoint, stats in latency_stats.items():
                    await db.execute(
                        """
                        INSERT INTO performance_metrics
                        (id, timestamp, metric_type, component, value, p50, p95, p99)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid4()),
                            timestamp,
                            "latency",
                            endpoint,
                            stats.mean,
                            stats.p50,
                            stats.p95,
                            stats.p99,
                        ),
                    )

                # Save throughput metrics
                for component, stats in throughput_stats.items():
                    await db.execute(
                        """
                        INSERT INTO performance_metrics
                        (id, timestamp, metric_type, component, value, p50, p95, p99)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid4()),
                            timestamp,
                            "throughput",
                            component,
                            stats["rps"],
                            stats["success_rate"],
                            stats["error_rate"],
                            0,
                        ),
                    )

                # Save resource metrics
                await db.execute(
                    """
                    INSERT INTO performance_metrics
                    (id, timestamp, metric_type, component, value, p50, p95, p99)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        timestamp,
                        "resource",
                        "cpu",
                        resource_stats["cpu_percent"]["current"],
                        resource_stats["cpu_percent"]["avg"],
                        resource_stats["cpu_percent"]["max"],
                        0,
                    ),
                )

                await db.execute(
                    """
                    INSERT INTO performance_metrics
                    (id, timestamp, metric_type, component, value, p50, p95, p99)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid4()),
                        timestamp,
                        "resource",
                        "memory",
                        resource_stats["memory_percent"]["current"],
                        resource_stats["memory_percent"]["avg"],
                        resource_stats["memory_percent"]["max"],
                        0,
                    ),
                )

                await db.commit()

        except Exception as e:
            logger.error(f"Error saving metrics to DB: {e}")

    # ========== Dashboard API Methods ==========

    async def get_performance_summary(self) -> Dict[str, Any]:
        """Get overall performance summary"""
        latency_stats = self.get_latency_stats(minutes=5)
        throughput_stats = self.get_throughput_stats(minutes=5)
        resource_stats = self.get_resource_stats(minutes=5)
        bottlenecks = self.identify_bottlenecks()

        # Aggregate latency across all endpoints
        all_latencies = []
        for stats in latency_stats.values():
            all_latencies.extend([stats.p50, stats.p95, stats.p99])

        avg_p95 = sum(s.p95 for s in latency_stats.values()) / len(latency_stats) if latency_stats else 0

        # Aggregate throughput
        total_rps = sum(s["rps"] for s in throughput_stats.values())
        avg_success_rate = sum(s["success_rate"] for s in throughput_stats.values()) / len(throughput_stats) if throughput_stats else 0

        return {
            "timestamp": datetime.now().isoformat(),
            "latency": {
                "avg_p95_ms": avg_p95,
                "endpoint_count": len(latency_stats),
            },
            "throughput": {
                "total_rps": total_rps,
                "avg_success_rate": avg_success_rate,
            },
            "resources": resource_stats,
            "bottlenecks": [
                {
                    "type": b.type,
                    "component": b.component,
                    "description": b.description,
                    "severity": b.severity,
                }
                for b in bottlenecks
            ],
            "health": "healthy" if len([b for b in bottlenecks if b.severity in ["HIGH", "CRITICAL"]]) == 0 else "degraded",
        }

    async def get_latency_analysis(self) -> Dict[str, Any]:
        """Get detailed latency analysis"""
        stats = self.get_latency_stats(minutes=15)

        return {
            "timestamp": datetime.now().isoformat(),
            "window_minutes": 15,
            "endpoints": {
                endpoint: {
                    "p50": s.p50,
                    "p95": s.p95,
                    "p99": s.p99,
                    "mean": s.mean,
                    "min": s.min,
                    "max": s.max,
                    "count": s.count,
                }
                for endpoint, s in stats.items()
            },
        }

    async def get_throughput_analysis(self) -> Dict[str, Any]:
        """Get detailed throughput analysis"""
        stats = self.get_throughput_stats(minutes=15)

        return {
            "timestamp": datetime.now().isoformat(),
            "window_minutes": 15,
            "components": stats,
        }

    async def get_bottlenecks_analysis(self) -> Dict[str, Any]:
        """Get detailed bottleneck analysis"""
        bottlenecks = self.identify_bottlenecks()
        slow_queries = await self.get_slow_queries_from_db(limit=10)

        return {
            "timestamp": datetime.now().isoformat(),
            "bottlenecks": [
                {
                    "type": b.type,
                    "component": b.component,
                    "description": b.description,
                    "severity": b.severity,
                    "metrics": b.metrics,
                    "timestamp": b.timestamp.isoformat(),
                }
                for b in bottlenecks
            ],
            "slow_queries": slow_queries,
        }


# ========== Decorators ==========

# Global tracker instance (initialized by app)
_tracker: Optional[PerformanceTracker] = None


def set_global_tracker(tracker: PerformanceTracker):
    """Set global tracker instance"""
    global _tracker
    _tracker = tracker


def track_performance(func: Callable) -> Callable:
    """
    Decorator to track function performance.

    Usage:
        @track_performance
        async def my_function():
            pass
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        if _tracker is None:
            return await func(*args, **kwargs)

        start = time.time()
        success = True
        error_type = None

        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            success = False
            error_type = type(e).__name__
            raise
        finally:
            latency_ms = (time.time() - start) * 1000
            _tracker.track_latency(
                component=func.__module__ or "unknown",
                endpoint=func.__name__,
                latency_ms=latency_ms,
                success=success,
                error_type=error_type,
            )

    return wrapper


def track_latency(endpoint: str, component: str = "api"):
    """
    Decorator to track endpoint latency.

    Usage:
        @track_latency("api_endpoint")
        async def handle_request():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            if _tracker is None:
                return await func(*args, **kwargs)

            start = time.time()
            success = True
            error_type = None

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                success = False
                error_type = type(e).__name__
                raise
            finally:
                latency_ms = (time.time() - start) * 1000
                _tracker.track_latency(
                    component=component,
                    endpoint=endpoint,
                    latency_ms=latency_ms,
                    success=success,
                    error_type=error_type,
                )

        return wrapper
    return decorator
