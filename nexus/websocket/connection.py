"""WebSocket connection wrapper with async iteration support."""

from __future__ import annotations

import json
from typing import Any


class WebSocketConnection:
    """
    Async wrapper around a raw ASGI WebSocket connection.

    Usage::

        @app.websocket("/ws")
        async def ws_handler(scope, receive, send):
            ws = WebSocketConnection(scope, receive, send)
            await ws.accept()
            async for message in ws:
                await ws.send_text(f"Echo: {message}")
    """

    def __init__(self, scope: dict, receive: Any, send: Any) -> None:
        self._scope = scope
        self._receive = receive
        self._send = send
        self._accepted = False
        self._closed = False

    async def accept(self, subprotocol: str | None = None) -> None:
        """Accept the WebSocket connection."""
        await self._send(
            {
                "type": "websocket.accept",
                "subprotocol": subprotocol,
            }
        )
        self._accepted = True

    async def send_text(self, data: str) -> None:
        """Send a text message."""
        await self._send({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        """Send a binary message."""
        await self._send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any) -> None:
        """Serialize *data* to JSON and send as text."""
        await self.send_text(json.dumps(data, default=str))

    async def receive_text(self) -> str | None:
        """Receive a text message, or None if connection closed."""
        msg = await self._receive()
        if msg["type"] == "websocket.disconnect":
            self._closed = True
            return None
        return msg.get("text") or (msg.get("bytes", b"").decode())

    async def receive_json(self) -> Any | None:
        """Receive and parse a JSON message."""
        text = await self.receive_text()
        if text is None:
            return None
        return json.loads(text)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """Close the connection."""
        if not self._closed:
            await self._send({"type": "websocket.close", "code": code, "reason": reason})
            self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def path_params(self) -> dict[str, Any]:
        return self._scope.get("path_params", {})

    @property
    def headers(self) -> dict[str, str]:
        raw = self._scope.get("headers", [])
        return {k.decode(): v.decode() for k, v in raw}

    def __aiter__(self) -> "WebSocketConnection":
        return self

    async def __anext__(self) -> str:
        """Iterate over incoming text messages; stops when connection closes."""
        msg = await self.receive_text()
        if msg is None:
            raise StopAsyncIteration
        return msg
