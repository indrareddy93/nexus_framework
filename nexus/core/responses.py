"""HTTP Response classes for Nexus."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator


class Response:
    """Base HTTP response."""

    media_type: str = "application/octet-stream"

    def __init__(
        self,
        content: bytes = b"",
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.body = content
        self.status_code = status_code
        self._headers = headers or {}

    def _build_headers(self) -> list[tuple[bytes, bytes]]:
        h: list[tuple[bytes, bytes]] = [
            (b"content-type", self.media_type.encode()),
            (b"content-length", str(len(self.body)).encode()),
        ]
        for k, v in self._headers.items():
            h.append((k.lower().encode(), v.encode()))
        return h

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )
        await send({"type": "http.response.body", "body": self.body})


class JSONResponse(Response):
    """Serialize a dict/list to JSON and set Content-Type: application/json."""

    media_type = "application/json"

    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(content, default=str).encode("utf-8")
        super().__init__(body, status_code, headers)


class HTMLResponse(Response):
    """Return raw HTML."""

    media_type = "text/html; charset=utf-8"

    def __init__(
        self,
        content: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(content.encode("utf-8"), status_code, headers)


class PlainTextResponse(Response):
    """Return plain text."""

    media_type = "text/plain; charset=utf-8"

    def __init__(
        self,
        content: str,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(content.encode("utf-8"), status_code, headers)


class RedirectResponse(Response):
    """HTTP redirect."""

    def __init__(self, url: str, status_code: int = 307) -> None:
        super().__init__(b"", status_code, {"location": url})


class StreamingResponse:
    """Stream an async generator as chunked HTTP response."""

    media_type = "application/octet-stream"

    def __init__(
        self,
        content: AsyncIterator[bytes | str],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        self._content = content
        self.status_code = status_code
        self._headers = headers or {}
        if media_type:
            self.media_type = media_type

    def _build_headers(self) -> list[tuple[bytes, bytes]]:
        h: list[tuple[bytes, bytes]] = [
            (b"content-type", self.media_type.encode()),
            (b"transfer-encoding", b"chunked"),
        ]
        for k, v in self._headers.items():
            h.append((k.lower().encode(), v.encode()))
        return h

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )
        async for chunk in self._content:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b""})
