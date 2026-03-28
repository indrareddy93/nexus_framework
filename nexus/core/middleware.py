"""Middleware base class and built-in middlewares."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from nexus.core.requests import Request
from nexus.core.responses import JSONResponse, Response

logger = logging.getLogger("nexus.middleware")


class Middleware:
    """
    Base middleware interface.

    Implement ``before_request`` to short-circuit the request (return a
    Response), or ``after_response`` to post-process the response.
    """

    async def before_request(self, request: Request) -> Response | None:
        """Return a Response to short-circuit, or None to continue."""
        return None

    async def after_response(self, request: Request, response: Any) -> Any:
        """Post-process the response. Must return a response-like object."""
        return response


# ── Built-in middlewares ────────────────────────────────────────────────────


class CORSMiddleware(Middleware):
    """
    Cross-Origin Resource Sharing (CORS).

    Usage::

        app.add_middleware(CORSMiddleware(allow_origins=["https://mysite.com"]))
    """

    def __init__(
        self,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        allow_credentials: bool = False,
        max_age: int = 600,
    ) -> None:
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
        self.max_age = max_age

    def _cors_headers(self, origin: str) -> dict[str, str]:
        allowed = "*" if "*" in self.allow_origins else (origin if origin in self.allow_origins else "")
        headers: dict[str, str] = {
            "access-control-allow-origin": allowed or "null",
            "access-control-allow-methods": ", ".join(self.allow_methods),
            "access-control-allow-headers": ", ".join(self.allow_headers),
            "access-control-max-age": str(self.max_age),
        }
        if self.allow_credentials:
            headers["access-control-allow-credentials"] = "true"
        return headers

    async def before_request(self, request: Request) -> Response | None:
        origin = request.headers.get("origin", "")
        if request.method == "OPTIONS":
            # Preflight
            return Response(b"", status_code=204, headers=self._cors_headers(origin))
        return None

    async def after_response(self, request: Request, response: Any) -> Any:
        origin = request.headers.get("origin", "")
        if origin and hasattr(response, "_headers"):
            for k, v in self._cors_headers(origin).items():
                response._headers.setdefault(k, v)
        return response


class LoggingMiddleware(Middleware):
    """Log every incoming request and its response status/time."""

    async def before_request(self, request: Request) -> None:
        request._scope["_start_time"] = time.monotonic()
        return None

    async def after_response(self, request: Request, response: Any) -> Any:
        elapsed = (time.monotonic() - request._scope.get("_start_time", time.monotonic())) * 1000
        status = getattr(response, "status_code", "?")
        logger.info("%s %s → %s (%.1fms)", request.method, request.path, status, elapsed)
        return response


class RateLimitMiddleware(Middleware):
    """
    Simple in-process token-bucket rate limiter (per client IP).

    Usage::

        app.add_middleware(RateLimitMiddleware(requests_per_minute=60))
    """

    def __init__(self, requests_per_minute: int = 60) -> None:
        self.rpm = requests_per_minute
        self._window = 60.0
        self._counts: dict[str, list[float]] = defaultdict(list)

    def _client_ip(self, request: Request) -> str:
        client = request.client
        return client[0] if client else "unknown"

    async def before_request(self, request: Request) -> Response | None:
        ip = self._client_ip(request)
        now = time.monotonic()
        window_start = now - self._window
        hits = [t for t in self._counts[ip] if t > window_start]
        if len(hits) >= self.rpm:
            return JSONResponse(
                {"error": "Rate limit exceeded", "retry_after": 60},
                status_code=429,
                headers={"retry-after": "60"},
            )
        hits.append(now)
        self._counts[ip] = hits
        return None


class TrustedHostMiddleware(Middleware):
    """Reject requests whose Host header doesn't match the allowed list."""

    def __init__(self, allowed_hosts: list[str]) -> None:
        self.allowed = set(allowed_hosts)

    async def before_request(self, request: Request) -> Response | None:
        host = request.headers.get("host", "").split(":")[0]
        if self.allowed and host not in self.allowed:
            return JSONResponse({"error": "Invalid host"}, status_code=400)
        return None


class GZipMiddleware(Middleware):
    """Compress responses with gzip when the client accepts it."""

    def __init__(self, minimum_size: int = 500) -> None:
        self.minimum_size = minimum_size

    async def after_response(self, request: Request, response: Any) -> Any:
        accept = request.headers.get("accept-encoding", "")
        if "gzip" not in accept:
            return response
        if isinstance(response, Response) and len(response.body) >= self.minimum_size:
            import gzip

            response.body = gzip.compress(response.body)
            response._headers["content-encoding"] = "gzip"
            response._headers["content-length"] = str(len(response.body))
        return response
