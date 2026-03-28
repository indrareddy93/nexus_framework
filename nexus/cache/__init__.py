"""nexus.cache package — in-memory caching with TTL and @cached decorator."""

from nexus.cache.backend import InMemoryCache, cached

__all__ = ["InMemoryCache", "cached"]
