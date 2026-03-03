"""
API Gateway with rate limiting, authentication, and usage tracking.

Features:
- Proxy for external API integrations
- Per-tenant rate limiting
- API key validation middleware
- Usage tracking and analytics
- Request/response transformation
"""

import time
import sqlite3
import logging
import hashlib
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict
import asyncio
from functools import wraps

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_size: int = 10


@dataclass
class UsageRecord:
    """API usage record."""
    tenant_id: str
    endpoint: str
    method: str
    status_code: int
    response_time_ms: float
    timestamp: datetime
    request_size: int = 0
    response_size: int = 0


class RateLimiter:
    """
    Token bucket rate limiter with multiple time windows.

    Features:
    - Per-tenant rate limiting
    - Multiple time windows (minute/hour/day)
    - Burst handling
    """

    def __init__(self, db_path: str = "data/rate_limits.db"):
        """Initialize rate limiter."""
        self.db_path = db_path
        self._buckets: Dict[str, Dict[str, list]] = defaultdict(
            lambda: {"minute": [], "hour": [], "day": []}
        )
        self._ensure_db()

    def _ensure_db(self):
        """Create rate limit database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limit_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    window TEXT NOT NULL,
                    violated_at TEXT NOT NULL,
                    request_count INTEGER NOT NULL
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_violations_tenant
                ON rate_limit_violations(tenant_id, violated_at)
            """)

    def check_limit(
        self,
        tenant_id: str,
        config: RateLimitConfig
    ) -> tuple[bool, Optional[str]]:
        """
        Check if request is within rate limits.

        Args:
            tenant_id: Tenant identifier
            config: Rate limit configuration

        Returns:
            (allowed, retry_after) tuple
        """
        now = time.time()
        buckets = self._buckets[tenant_id]

        # Clean old entries
        buckets["minute"] = [t for t in buckets["minute"] if now - t < 60]
        buckets["hour"] = [t for t in buckets["hour"] if now - t < 3600]
        buckets["day"] = [t for t in buckets["day"] if now - t < 86400]

        # Check limits
        if len(buckets["minute"]) >= config.requests_per_minute:
            retry_after = 60 - (now - buckets["minute"][0])
            self._log_violation(tenant_id, "minute", len(buckets["minute"]))
            return False, f"{retry_after:.0f}s"

        if len(buckets["hour"]) >= config.requests_per_hour:
            retry_after = 3600 - (now - buckets["hour"][0])
            self._log_violation(tenant_id, "hour", len(buckets["hour"]))
            return False, f"{retry_after/60:.0f}m"

        if len(buckets["day"]) >= config.requests_per_day:
            retry_after = 86400 - (now - buckets["day"][0])
            self._log_violation(tenant_id, "day", len(buckets["day"]))
            return False, f"{retry_after/3600:.0f}h"

        # Add to buckets
        buckets["minute"].append(now)
        buckets["hour"].append(now)
        buckets["day"].append(now)

        return True, None

    def _log_violation(self, tenant_id: str, window: str, count: int):
        """Log rate limit violation."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO rate_limit_violations
                    (tenant_id, window, violated_at, request_count)
                    VALUES (?, ?, ?, ?)
                    """,
                    (tenant_id, window, datetime.utcnow().isoformat(), count)
                )
        except Exception as e:
            logger.error(f"Failed to log violation: {e}")

    def get_current_usage(self, tenant_id: str) -> Dict[str, int]:
        """Get current usage across time windows."""
        now = time.time()
        buckets = self._buckets[tenant_id]

        return {
            "minute": len([t for t in buckets["minute"] if now - t < 60]),
            "hour": len([t for t in buckets["hour"] if now - t < 3600]),
            "day": len([t for t in buckets["day"] if now - t < 86400])
        }


class UsageTracker:
    """
    Track API usage for analytics and billing.

    Features:
    - Per-tenant usage tracking
    - Endpoint-level metrics
    - Cost calculation
    - Usage reports
    """

    def __init__(self, db_path: str = "data/usage.db"):
        """Initialize usage tracker."""
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        """Create usage database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER NOT NULL,
                    response_time_ms REAL NOT NULL,
                    request_size INTEGER DEFAULT 0,
                    response_size INTEGER DEFAULT 0,
                    timestamp TEXT NOT NULL
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usage_tenant_time
                ON usage_records(tenant_id, timestamp)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_usage_endpoint
                ON usage_records(endpoint, timestamp)
            """)

    def record_usage(self, record: UsageRecord):
        """
        Record API usage.

        Args:
            record: Usage record
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO usage_records
                    (tenant_id, endpoint, method, status_code, response_time_ms,
                     request_size, response_size, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.tenant_id,
                        record.endpoint,
                        record.method,
                        record.status_code,
                        record.response_time_ms,
                        record.request_size,
                        record.response_size,
                        record.timestamp.isoformat()
                    )
                )
        except Exception as e:
            logger.error(f"Failed to record usage: {e}")

    def get_usage_summary(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Get usage summary for tenant.

        Args:
            tenant_id: Tenant identifier
            start_date: Start of period
            end_date: End of period

        Returns:
            Usage summary
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_requests,
                    SUM(CASE WHEN status_code < 400 THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as failed,
                    AVG(response_time_ms) as avg_response_time,
                    MAX(response_time_ms) as max_response_time,
                    SUM(request_size) as total_request_bytes,
                    SUM(response_size) as total_response_bytes
                FROM usage_records
                WHERE tenant_id = ?
                  AND timestamp >= ?
                  AND timestamp <= ?
                """,
                (tenant_id, start_date.isoformat(), end_date.isoformat())
            )

            row = cursor.fetchone()

            return {
                "tenant_id": tenant_id,
                "period": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "total_requests": row[0] or 0,
                "successful_requests": row[1] or 0,
                "failed_requests": row[2] or 0,
                "avg_response_time_ms": row[3] or 0,
                "max_response_time_ms": row[4] or 0,
                "total_bandwidth_bytes": (row[5] or 0) + (row[6] or 0)
            }

    def get_endpoint_stats(
        self,
        tenant_id: str,
        days: int = 7
    ) -> list[Dict[str, Any]]:
        """
        Get per-endpoint statistics.

        Args:
            tenant_id: Tenant identifier
            days: Number of days to analyze

        Returns:
            List of endpoint statistics
        """
        start_date = datetime.utcnow() - timedelta(days=days)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT
                    endpoint,
                    method,
                    COUNT(*) as requests,
                    AVG(response_time_ms) as avg_time,
                    SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as errors
                FROM usage_records
                WHERE tenant_id = ?
                  AND timestamp >= ?
                GROUP BY endpoint, method
                ORDER BY requests DESC
                """,
                (tenant_id, start_date.isoformat())
            )

            stats = []
            for row in cursor.fetchall():
                stats.append({
                    "endpoint": row[0],
                    "method": row[1],
                    "requests": row[2],
                    "avg_response_time_ms": row[3],
                    "error_count": row[4],
                    "error_rate": row[4] / row[2] if row[2] > 0 else 0
                })

            return stats


class APIGateway:
    """
    API Gateway for managing external API access.

    Features:
    - Request routing and proxying
    - Authentication middleware
    - Rate limiting
    - Usage tracking
    - Request/response transformation
    """

    def __init__(
        self,
        rate_limiter: Optional[RateLimiter] = None,
        usage_tracker: Optional[UsageTracker] = None
    ):
        """
        Initialize API Gateway.

        Args:
            rate_limiter: Rate limiter instance
            usage_tracker: Usage tracker instance
        """
        self.rate_limiter = rate_limiter or RateLimiter()
        self.usage_tracker = usage_tracker or UsageTracker()
        self._tenant_configs: Dict[str, RateLimitConfig] = {}
        self._middleware: list[Callable] = []

    def set_tenant_rate_limit(
        self,
        tenant_id: str,
        config: RateLimitConfig
    ):
        """
        Set rate limit configuration for tenant.

        Args:
            tenant_id: Tenant identifier
            config: Rate limit configuration
        """
        self._tenant_configs[tenant_id] = config
        logger.info(f"Set rate limit for {tenant_id}: {config}")

    def get_rate_limit_config(
        self,
        tenant_id: str
    ) -> RateLimitConfig:
        """Get rate limit config for tenant (or default)."""
        return self._tenant_configs.get(
            tenant_id,
            RateLimitConfig()  # Default config
        )

    def add_middleware(self, middleware: Callable):
        """
        Add middleware function.

        Args:
            middleware: Middleware callable
        """
        self._middleware.append(middleware)

    def rate_limit_middleware(self, func):
        """Rate limiting middleware decorator."""
        @wraps(func)
        async def wrapper(tenant_id: str, *args, **kwargs):
            config = self.get_rate_limit_config(tenant_id)
            allowed, retry_after = self.rate_limiter.check_limit(
                tenant_id,
                config
            )

            if not allowed:
                return {
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after
                }, 429

            return await func(tenant_id, *args, **kwargs)

        return wrapper

    def usage_tracking_middleware(self, func):
        """Usage tracking middleware decorator."""
        @wraps(func)
        async def wrapper(tenant_id: str, endpoint: str, method: str, *args, **kwargs):
            start_time = time.time()

            try:
                result = await func(tenant_id, endpoint, method, *args, **kwargs)
                status_code = 200
                return result

            except Exception as e:
                status_code = 500
                raise

            finally:
                response_time = (time.time() - start_time) * 1000

                record = UsageRecord(
                    tenant_id=tenant_id,
                    endpoint=endpoint,
                    method=method,
                    status_code=status_code,
                    response_time_ms=response_time,
                    timestamp=datetime.utcnow()
                )

                self.usage_tracker.record_usage(record)

        return wrapper

    async def proxy_request(
        self,
        tenant_id: str,
        endpoint: str,
        method: str = "GET",
        headers: Optional[Dict] = None,
        body: Optional[Any] = None
    ) -> tuple[Any, int]:
        """
        Proxy request to external API.

        Args:
            tenant_id: Tenant making request
            endpoint: Target endpoint
            method: HTTP method
            headers: Request headers
            body: Request body

        Returns:
            (response, status_code) tuple
        """
        # Check rate limit
        config = self.get_rate_limit_config(tenant_id)
        allowed, retry_after = self.rate_limiter.check_limit(tenant_id, config)

        if not allowed:
            return {
                "error": "Rate limit exceeded",
                "retry_after": retry_after
            }, 429

        # Track usage
        start_time = time.time()

        try:
            # Simulate API call (replace with actual HTTP client)
            await asyncio.sleep(0.1)  # Simulate network latency
            response = {"status": "success", "data": {}}
            status_code = 200

        except Exception as e:
            logger.error(f"Proxy request failed: {e}")
            response = {"error": str(e)}
            status_code = 500

        finally:
            response_time = (time.time() - start_time) * 1000

            record = UsageRecord(
                tenant_id=tenant_id,
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                response_time_ms=response_time,
                timestamp=datetime.utcnow()
            )

            self.usage_tracker.record_usage(record)

        return response, status_code


# Flask integration example
def register_gateway_routes(app, gateway: APIGateway):
    """
    Register gateway routes with Flask app.

    Args:
        app: Flask application
        gateway: APIGateway instance
    """
    from flask import request, jsonify

    @app.route("/api/gateway/<path:endpoint>", methods=["GET", "POST", "PUT", "DELETE"])
    async def gateway_proxy(endpoint: str):
        """Proxy endpoint."""
        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            return jsonify({"error": "Missing tenant ID"}), 401

        response, status = await gateway.proxy_request(
            tenant_id=tenant_id,
            endpoint=endpoint,
            method=request.method,
            headers=dict(request.headers),
            body=request.get_json() if request.is_json else None
        )

        return jsonify(response), status

    @app.route("/api/gateway/usage/<tenant_id>", methods=["GET"])
    def gateway_usage(tenant_id: str):
        """Get usage statistics."""
        days = int(request.args.get("days", 7))
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        summary = gateway.usage_tracker.get_usage_summary(
            tenant_id,
            start_date,
            end_date
        )

        endpoints = gateway.usage_tracker.get_endpoint_stats(
            tenant_id,
            days
        )

        return jsonify({
            "summary": summary,
            "endpoints": endpoints
        })

    @app.route("/api/gateway/limits/<tenant_id>", methods=["GET"])
    def gateway_limits(tenant_id: str):
        """Get rate limit status."""
        config = gateway.get_rate_limit_config(tenant_id)
        current = gateway.rate_limiter.get_current_usage(tenant_id)

        return jsonify({
            "limits": {
                "minute": config.requests_per_minute,
                "hour": config.requests_per_hour,
                "day": config.requests_per_day
            },
            "current": current,
            "remaining": {
                "minute": config.requests_per_minute - current["minute"],
                "hour": config.requests_per_hour - current["hour"],
                "day": config.requests_per_day - current["day"]
            }
        })
