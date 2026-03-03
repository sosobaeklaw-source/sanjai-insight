"""
Redis Caching Layer
Optional Redis client for LLM response caching and Obsidian metadata caching.
Falls back to in-memory cache if Redis is not available.
"""

import hashlib
import json
import logging
import os
from typing import Any, Optional
from datetime import timedelta

logger = logging.getLogger(__name__)


class CacheClient:
    """Base cache client interface"""

    def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value with optional TTL (seconds)"""
        raise NotImplementedError

    def delete(self, key: str):
        """Delete key"""
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        """Check if key exists"""
        raise NotImplementedError

    def clear(self):
        """Clear all keys"""
        raise NotImplementedError


class RedisCache(CacheClient):
    """Redis cache client"""

    def __init__(self, redis_url: Optional[str] = None, default_ttl: int = 3600):
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.default_ttl = default_ttl
        self._client = None

        if not self.redis_url:
            logger.warning("REDIS_URL not configured, Redis cache disabled")
            return

        try:
            import redis
            self._client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True
            )
            # Test connection
            self._client.ping()
            logger.info("Redis cache connected: %s", self.redis_url)
        except ImportError:
            logger.warning("redis package not installed, Redis cache disabled")
            self._client = None
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self._client = None

    @property
    def enabled(self) -> bool:
        """Check if Redis is enabled and connected"""
        return self._client is not None

    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis"""
        if not self.enabled:
            return None

        try:
            value = self._client.get(key)
            if value is None:
                return None

            # Try to deserialize JSON
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value

        except Exception as e:
            logger.error("Redis GET error for key %s: %s", key, e)
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in Redis with TTL"""
        if not self.enabled:
            return

        try:
            # Serialize value
            if isinstance(value, (dict, list)):
                serialized = json.dumps(value)
            else:
                serialized = str(value)

            # Set with TTL
            ttl = ttl or self.default_ttl
            self._client.setex(key, ttl, serialized)

        except Exception as e:
            logger.error("Redis SET error for key %s: %s", key, e)

    def delete(self, key: str):
        """Delete key from Redis"""
        if not self.enabled:
            return

        try:
            self._client.delete(key)
        except Exception as e:
            logger.error("Redis DELETE error for key %s: %s", key, e)

    def exists(self, key: str) -> bool:
        """Check if key exists in Redis"""
        if not self.enabled:
            return False

        try:
            return bool(self._client.exists(key))
        except Exception as e:
            logger.error("Redis EXISTS error for key %s: %s", key, e)
            return False

    def clear(self):
        """Clear all keys (use with caution)"""
        if not self.enabled:
            return

        try:
            self._client.flushdb()
            logger.warning("Redis cache cleared")
        except Exception as e:
            logger.error("Redis CLEAR error: %s", e)

    def get_stats(self) -> dict:
        """Get cache statistics"""
        if not self.enabled:
            return {"enabled": False}

        try:
            info = self._client.info("stats")
            return {
                "enabled": True,
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": info.get("keyspace_hits", 0) / max(
                    info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1
                ),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": self._client.info("memory").get("used_memory_human", "unknown")
            }
        except Exception as e:
            logger.error("Redis STATS error: %s", e)
            return {"enabled": True, "error": str(e)}


class InMemoryCache(CacheClient):
    """In-memory fallback cache"""

    def __init__(self, max_size: int = 1000):
        self._cache = {}
        self._max_size = max_size
        logger.info("Using in-memory cache (max size: %d)", max_size)

    def get(self, key: str) -> Optional[Any]:
        """Get value from memory"""
        entry = self._cache.get(key)
        if entry is None:
            return None

        # Check expiration
        import time
        value, expires_at = entry
        if expires_at and time.time() > expires_at:
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in memory with TTL"""
        import time

        # Evict oldest if cache is full
        if len(self._cache) >= self._max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        expires_at = time.time() + ttl if ttl else None
        self._cache[key] = (value, expires_at)

    def delete(self, key: str):
        """Delete key from memory"""
        if key in self._cache:
            del self._cache[key]

    def exists(self, key: str) -> bool:
        """Check if key exists in memory"""
        return self.get(key) is not None

    def clear(self):
        """Clear all keys"""
        self._cache.clear()
        logger.info("In-memory cache cleared")


# Global cache instance
_cache_instance: Optional[CacheClient] = None


def get_cache() -> CacheClient:
    """Get global cache instance"""
    global _cache_instance

    if _cache_instance is None:
        # Try Redis first
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            redis_cache = RedisCache(redis_url)
            if redis_cache.enabled:
                _cache_instance = redis_cache
            else:
                _cache_instance = InMemoryCache()
        else:
            _cache_instance = InMemoryCache()

    return _cache_instance


def cache_llm_response(
    model: str,
    prompt: str,
    response: dict,
    ttl: int = 86400  # 24 hours
):
    """
    Cache LLM response using dedupe_key.

    Args:
        model: Model name
        prompt: Input prompt
        response: LLM response dict
        ttl: Time to live in seconds (default 24h)
    """
    cache = get_cache()

    # Generate cache key from model + prompt hash
    key_data = f"{model}:{prompt}"
    cache_key = f"llm:{hashlib.sha256(key_data.encode()).hexdigest()}"

    cache.set(cache_key, response, ttl)


def get_cached_llm_response(model: str, prompt: str) -> Optional[dict]:
    """
    Get cached LLM response.

    Args:
        model: Model name
        prompt: Input prompt

    Returns:
        Cached response dict or None
    """
    cache = get_cache()

    # Generate cache key
    key_data = f"{model}:{prompt}"
    cache_key = f"llm:{hashlib.sha256(key_data.encode()).hexdigest()}"

    return cache.get(cache_key)


def cache_vault_metadata(vault_path: str, metadata: dict, ttl: int = 3600):
    """
    Cache Obsidian vault metadata.

    Args:
        vault_path: Path to vault
        metadata: Vault metadata dict
        ttl: Time to live in seconds (default 1h)
    """
    cache = get_cache()

    cache_key = f"vault:{hashlib.sha256(vault_path.encode()).hexdigest()}"
    cache.set(cache_key, metadata, ttl)


def get_cached_vault_metadata(vault_path: str) -> Optional[dict]:
    """
    Get cached vault metadata.

    Args:
        vault_path: Path to vault

    Returns:
        Cached metadata dict or None
    """
    cache = get_cache()

    cache_key = f"vault:{hashlib.sha256(vault_path.encode()).hexdigest()}"
    return cache.get(cache_key)


def invalidate_vault_cache(vault_path: str):
    """Invalidate cached vault metadata"""
    cache = get_cache()

    cache_key = f"vault:{hashlib.sha256(vault_path.encode()).hexdigest()}"
    cache.delete(cache_key)


def clear_all_caches():
    """Clear all caches (use with caution)"""
    cache = get_cache()
    cache.clear()


def get_cache_stats() -> dict:
    """Get cache statistics"""
    cache = get_cache()

    if isinstance(cache, RedisCache):
        return cache.get_stats()
    elif isinstance(cache, InMemoryCache):
        return {
            "enabled": True,
            "type": "in-memory",
            "size": len(cache._cache),
            "max_size": cache._max_size
        }
    else:
        return {"enabled": False}
