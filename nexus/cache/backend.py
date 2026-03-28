"""In-memory cache with TTL support."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable


class CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, expires_at: float) -> None:
        self.value = value
        self.expires_at = expires_at

    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


class InMemoryCache:
    """
    Thread-safe in-memory cache with per-key TTL and a get_or_set helper.

    Usage::

        cache = InMemoryCache(default_ttl=300)
        await cache.set("key", "value")
        value = await cache.get("key")
        await cache.delete("key")
        result = await cache.get_or_set("expensive", lambda: compute())
    """

    def __init__(self, default_ttl: float = 300) -> None:
        self.default_ttl = default_ttl
        self._store: dict[str, CacheEntry] = {}

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Store a value with an optional TTL (seconds)."""
        effective_ttl = ttl if ttl is not None else self.default_ttl
        expires_at = time.monotonic() + effective_ttl
        self._store[key] = CacheEntry(value, expires_at)

    async def get(self, key: str, default: Any = None) -> Any:
        """Return cached value or *default* if missing / expired."""
        entry = self._store.get(key)
        if entry is None or entry.is_expired():
            self._store.pop(key, None)
            return default
        return entry.value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        entry = self._store.get(key)
        if entry is None or entry.is_expired():
            return False
        return True

    async def get_or_set(
        self, key: str, factory: Callable, ttl: float | None = None
    ) -> Any:
        """
        Return cached value; if missing, call *factory()* and cache the result.

        *factory* may be a regular callable or a coroutine function.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached
        value = factory()
        if asyncio.iscoroutine(value):
            value = await value
        await self.set(key, value, ttl=ttl)
        return value

    async def clear(self) -> None:
        """Remove all entries."""
        self._store.clear()

    async def clear_expired(self) -> int:
        """Remove expired entries, return count removed."""
        expired = [k for k, v in self._store.items() if v.is_expired()]
        for k in expired:
            del self._store[k]
        return len(expired)

    def size(self) -> int:
        """Return count of non-expired entries."""
        now = time.monotonic()
        return sum(1 for v in self._store.values() if v.expires_at > now)

    def __repr__(self) -> str:
        return f"<InMemoryCache size={self.size()} ttl={self.default_ttl}>"


# ── @cached decorator ────────────────────────────────────────────────────────

def cached(cache_instance: InMemoryCache, ttl: float | None = None, key_prefix: str = "") -> Callable:
    """
    Decorator that caches the return value of an async handler.

    Usage::

        @app.get("/data")
        @cached(cache, ttl=60)
        async def expensive_handler():
            return compute_heavy_data()
    """
    def decorator(fn: Callable) -> Callable:
        import functools

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = key_prefix + fn.__name__ + str(args) + str(sorted(kwargs.items()))
            cached_val = await cache_instance.get(cache_key)
            if cached_val is not None:
                return cached_val
            result = await fn(*args, **kwargs)
            await cache_instance.set(cache_key, result, ttl=ttl)
            return result

        return wrapper

    return decorator
