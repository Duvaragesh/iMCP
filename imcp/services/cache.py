"""Caching service using cachetools."""
from typing import Any, Optional
from cachetools import TTLCache
import logging
from ._settings import imcp_setting

logger = logging.getLogger(__name__)


class CacheService:
    """TTL-based cache for tool definitions."""

    def __init__(self, max_size: int = None, ttl: int = None):
        """Initialize cache with TTL."""
        self.max_size = max_size or imcp_setting("CACHE_MAX_SIZE")
        self.ttl = ttl or imcp_setting("CACHE_TTL_SECONDS")
        self._cache = TTLCache(maxsize=self.max_size, ttl=self.ttl)
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        try:
            value = self._cache[key]
            self._hits += 1
            logger.debug(f"Cache HIT for key: {key}")
            return value
        except KeyError:
            self._misses += 1
            logger.debug(f"Cache MISS for key: {key}")
            return None

    def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        self._cache[key] = value
        logger.debug(f"Cache SET for key: {key}")

    def delete(self, key: str) -> None:
        """Delete key from cache."""
        try:
            del self._cache[key]
            logger.debug(f"Cache DELETE for key: {key}")
        except KeyError:
            pass

    def clear(self) -> None:
        """Clear all cache."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
        logger.info("Cache cleared")

    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl": self.ttl,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(hit_rate, 2),
        }


# Global cache instance
cache = CacheService()


def get_cached_tools(service_id: str) -> Optional[Any]:
    """Get cached tools for a service."""
    return cache.get(f"tools:{service_id}")


def set_cached_tools(service_id: str, tools: Any) -> None:
    """Cache tools for a service."""
    cache.set(f"tools:{service_id}", tools)


def invalidate_service_cache(service_id: str) -> None:
    """Invalidate cache for a service."""
    cache.delete(f"tools:{service_id}")


def get_cache_stats() -> dict:
    """Get cache statistics."""
    return cache.get_stats()
