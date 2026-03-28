"""HTTP Request wrapper over raw ASGI scope/receive."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs


class Request:
    """
    Wraps the raw ASGI scope and receive callable into a convenient object.

    Attributes
    ----------
    method  : HTTP verb (uppercase)
    path    : URL path
    headers : dict-like header access (lowercase keys)
    """

    __slots__ = ("_scope", "_receive", "_body", "_json_cache")

    def __init__(self, scope: dict, receive: Any) -> None:
        self._scope = scope
        self._receive = receive
        self._body: bytes | None = None
        self._json_cache: Any = None

    # ── Basic properties ────────────────────────────────────────────────────

    @property
    def method(self) -> str:
        return self._scope.get("method", "GET").upper()

    @property
    def path(self) -> str:
        return self._scope.get("path", "/")

    @property
    def headers(self) -> dict[str, str]:
        raw: list[tuple[bytes, bytes]] = self._scope.get("headers", [])
        return {k.decode(): v.decode() for k, v in raw}

    @property
    def path_params(self) -> dict[str, Any]:
        return self._scope.get("path_params", {})

    @property
    def client(self) -> tuple[str, int] | None:
        return self._scope.get("client")

    @property
    def app(self) -> Any:
        return self._scope.get("app")

    # ── Query string ────────────────────────────────────────────────────────

    def query(self, key: str, default: str | None = None) -> str | None:
        qs: bytes = self._scope.get("query_string", b"")
        params = parse_qs(qs.decode(), keep_blank_values=True)
        vals = params.get(key)
        return vals[0] if vals else default

    def query_params(self) -> dict[str, str]:
        qs: bytes = self._scope.get("query_string", b"")
        params = parse_qs(qs.decode(), keep_blank_values=True)
        return {k: v[0] for k, v in params.items()}

    # ── Body ────────────────────────────────────────────────────────────────

    async def body(self) -> bytes:
        """Read and cache the raw request body."""
        if self._body is None:
            if self._receive is None:
                self._body = b""
            else:
                chunks: list[bytes] = []
                while True:
                    msg = await self._receive()
                    chunks.append(msg.get("body", b""))
                    if not msg.get("more_body", False):
                        break
                self._body = b"".join(chunks)
        return self._body

    async def json(self) -> Any:
        """Parse body as JSON (cached)."""
        if self._json_cache is None:
            raw = await self.body()
            self._json_cache = json.loads(raw) if raw else {}
        return self._json_cache

    async def text(self) -> str:
        raw = await self.body()
        return raw.decode("utf-8", errors="replace")

    async def form(self) -> dict[str, str]:
        """Parse application/x-www-form-urlencoded body."""
        raw = await self.text()
        params = parse_qs(raw, keep_blank_values=True)
        return {k: v[0] for k, v in params.items()}

    def __repr__(self) -> str:
        return f"<Request {self.method} {self.path}>"
