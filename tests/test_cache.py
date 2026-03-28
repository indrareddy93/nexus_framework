"""Tests for nexus.cache (InMemoryCache, @cached decorator)."""

import asyncio
import pytest
from nexus.cache import InMemoryCache, cached


@pytest.mark.asyncio
async def test_set_get_delete():
    c = InMemoryCache(default_ttl=60)
    await c.set("key", "value")
    assert await c.get("key") == "value"
    await c.delete("key")
    assert await c.get("key") is None


@pytest.mark.asyncio
async def test_ttl_expiry():
    c = InMemoryCache()
    await c.set("k", "v", ttl=0)
    await asyncio.sleep(0.01)
    assert await c.get("k") is None


@pytest.mark.asyncio
async def test_get_or_set():
    c = InMemoryCache()
    r = await c.get_or_set("x", lambda: 99)
    assert r == 99
    r2 = await c.get_or_set("x", lambda: 0)
    assert r2 == 99  # cached value returned


@pytest.mark.asyncio
async def test_get_or_set_async_factory():
    c = InMemoryCache()

    async def async_factory():
        return "async_value"

    r = await c.get_or_set("y", async_factory)
    assert r == "async_value"


@pytest.mark.asyncio
async def test_default_value():
    c = InMemoryCache()
    r = await c.get("missing", default="fallback")
    assert r == "fallback"


@pytest.mark.asyncio
async def test_exists():
    c = InMemoryCache(default_ttl=60)
    assert not await c.exists("x")
    await c.set("x", 1)
    assert await c.exists("x")


@pytest.mark.asyncio
async def test_size():
    c = InMemoryCache(default_ttl=60)
    await c.set("a", 1)
    await c.set("b", 2)
    assert c.size() == 2
    await c.delete("a")
    assert c.size() == 1


@pytest.mark.asyncio
async def test_clear():
    c = InMemoryCache(default_ttl=60)
    await c.set("a", 1)
    await c.set("b", 2)
    await c.clear()
    assert c.size() == 0


@pytest.mark.asyncio
async def test_cached_decorator():
    c = InMemoryCache(default_ttl=60)
    call_count = 0

    @cached(c, ttl=60)
    async def expensive():
        nonlocal call_count
        call_count += 1
        return {"data": "result"}

    r1 = await expensive()
    r2 = await expensive()
    assert r1 == r2
    assert call_count == 1  # only called once
