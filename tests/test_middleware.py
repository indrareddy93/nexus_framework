"""Tests for nexus.core.middleware (CORS, RateLimit, Logging)."""

import pytest
from nexus.core.middleware import CORSMiddleware, RateLimitMiddleware, LoggingMiddleware
from nexus.core.requests import Request


def _make_request(method="GET", path="/", headers=None, client=None):
    raw_headers = []
    if headers:
        raw_headers = [(k.encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": raw_headers,
        "query_string": b"",
    }
    if client:
        scope["client"] = client
    return Request(scope, None)


@pytest.mark.asyncio
async def test_cors_preflight():
    mw = CORSMiddleware(allow_origins=["https://example.com"])
    req = _make_request(
        method="OPTIONS",
        path="/",
        headers={"origin": "https://example.com"},
    )
    resp = await mw.before_request(req)
    assert resp is not None
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cors_allows_wildcard():
    mw = CORSMiddleware(allow_origins=["*"])
    req = _make_request(
        method="OPTIONS",
        path="/",
        headers={"origin": "https://any.com"},
    )
    resp = await mw.before_request(req)
    assert resp is not None
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cors_normal_request_passes():
    mw = CORSMiddleware(allow_origins=["*"])
    req = _make_request(method="GET", path="/", headers={"origin": "https://any.com"})
    resp = await mw.before_request(req)
    assert resp is None  # normal request passes through


@pytest.mark.asyncio
async def test_rate_limit():
    mw = RateLimitMiddleware(requests_per_minute=2)
    req = _make_request(client=("127.0.0.1", 8000))
    assert await mw.before_request(req) is None
    assert await mw.before_request(req) is None
    resp = await mw.before_request(req)  # 3rd request should be rate-limited
    assert resp is not None
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_logging_middleware_passes():
    mw = LoggingMiddleware()
    req = _make_request()
    result = await mw.before_request(req)
    assert result is None  # logging middleware never short-circuits
