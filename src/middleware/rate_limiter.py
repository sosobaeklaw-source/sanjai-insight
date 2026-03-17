"""
Rate Limiting Middleware
Token bucket algorithm for API and webhook rate limiting.
"""

import time
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock
from typing import Dict, Optional


@dataclass
class TokenBucket:
    """Token bucket for rate limiting"""
    capacity: int  # Maximum tokens
    refill_rate: float  # Tokens per second
    tokens: float  # Current tokens
    last_refill: float  # Last refill timestamp

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if successful."""
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill

        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    def get_wait_time(self, tokens: int = 1) -> float:
        """Get time to wait before tokens are available"""
        self._refill()

        if self.tokens >= tokens:
            return 0.0

        tokens_needed = tokens - self.tokens
        return tokens_needed / self.refill_rate


class RateLimiter:
    """Rate limiter using token bucket algorithm"""

    def __init__(
        self,
        capacity: int = 1000,  # Max requests
        refill_rate: float = 1000 / 3600,  # 1000 per hour = ~0.278 per second
        cleanup_interval: int = 3600  # Cleanup old buckets every hour
    ):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.cleanup_interval = cleanup_interval

        self._buckets: Dict[str, TokenBucket] = {}
        self._lock = Lock()
        self._last_cleanup = time.time()

    def check_rate_limit(self, identifier: str, tokens: int = 1) -> tuple[bool, Optional[float]]:
        """
        Check if request is allowed under rate limit.

        Args:
            identifier: Unique identifier (e.g., IP address, user ID)
            tokens: Number of tokens to consume (default 1)

        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        with self._lock:
            # Cleanup old buckets periodically
            self._cleanup_if_needed()

            # Get or create bucket
            bucket = self._buckets.get(identifier)
            if bucket is None:
                bucket = TokenBucket(
                    capacity=self.capacity,
                    refill_rate=self.refill_rate,
                    tokens=self.capacity,
                    last_refill=time.time()
                )
                self._buckets[identifier] = bucket

            # Try to consume tokens
            if bucket.consume(tokens):
                return True, None

            # Rate limited - return wait time
            wait_time = bucket.get_wait_time(tokens)
            return False, wait_time

    def get_remaining(self, identifier: str) -> int:
        """Get remaining tokens for identifier"""
        with self._lock:
            bucket = self._buckets.get(identifier)
            if bucket is None:
                return self.capacity

            bucket._refill()
            return int(bucket.tokens)

    def reset(self, identifier: str):
        """Reset rate limit for identifier"""
        with self._lock:
            if identifier in self._buckets:
                del self._buckets[identifier]

    def _cleanup_if_needed(self):
        """Remove old buckets that are at full capacity (inactive)"""
        now = time.time()

        if now - self._last_cleanup < self.cleanup_interval:
            return

        # Remove buckets that are full and haven't been used recently
        to_remove = []
        for identifier, bucket in self._buckets.items():
            bucket._refill()
            if bucket.tokens >= self.capacity and (now - bucket.last_refill) > 3600:
                to_remove.append(identifier)

        for identifier in to_remove:
            del self._buckets[identifier]

        self._last_cleanup = now

    def get_stats(self) -> dict:
        """Get rate limiter statistics"""
        with self._lock:
            return {
                "total_buckets": len(self._buckets),
                "capacity": self.capacity,
                "refill_rate": self.refill_rate,
                "refill_rate_per_hour": self.refill_rate * 3600,
                "last_cleanup": self._last_cleanup
            }


# Global rate limiter instances
_ip_limiter = RateLimiter(capacity=1000, refill_rate=1000 / 3600)  # 1000 req/hour per IP
_user_limiter = RateLimiter(capacity=500, refill_rate=500 / 3600)  # 500 req/hour per user


def check_ip_rate_limit(ip: str, tokens: int = 1) -> tuple[bool, Optional[float]]:
    """Check IP-based rate limit"""
    return _ip_limiter.check_rate_limit(ip, tokens)


def check_user_rate_limit(user_id: str, tokens: int = 1) -> tuple[bool, Optional[float]]:
    """Check user-based rate limit"""
    return _user_limiter.check_rate_limit(user_id, tokens)


def get_ip_remaining(ip: str) -> int:
    """Get remaining tokens for IP"""
    return _ip_limiter.get_remaining(ip)


def get_user_remaining(user_id: str) -> int:
    """Get remaining tokens for user"""
    return _user_limiter.get_remaining(user_id)


def reset_ip_limit(ip: str):
    """Reset IP rate limit"""
    _ip_limiter.reset(ip)


def reset_user_limit(user_id: str):
    """Reset user rate limit"""
    _user_limiter.reset(user_id)


# FastAPI middleware integration
def create_rate_limit_middleware():
    """Create FastAPI rate limiting middleware"""
    from fastapi import Request, Response, status
    from fastapi.responses import JSONResponse

    async def rate_limit_middleware(request: Request, call_next):
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Check rate limit
        allowed, retry_after = check_ip_rate_limit(client_ip)

        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after
                },
                headers={
                    "Retry-After": str(int(retry_after or 60)),
                    "X-RateLimit-Limit": str(_ip_limiter.capacity),
                    "X-RateLimit-Remaining": "0"
                }
            )

        # Process request
        response: Response = await call_next(request)

        # Add rate limit headers
        remaining = get_ip_remaining(client_ip)
        response.headers["X-RateLimit-Limit"] = str(_ip_limiter.capacity)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response

    return rate_limit_middleware
