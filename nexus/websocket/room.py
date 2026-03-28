"""WebSocket pub/sub room for broadcasting to multiple connections."""

from __future__ import annotations

import logging
from typing import Any

from nexus.websocket.connection import WebSocketConnection

logger = logging.getLogger("nexus.websocket")


class WebSocketRoom:
    """
    Pub/sub room — broadcast messages to all connected WebSocket clients.

    Usage::

        chat = WebSocketRoom("general")

        @app.websocket("/ws/chat")
        async def ws_chat(scope, receive, send):
            ws = WebSocketConnection(scope, receive, send)
            await ws.accept()
            chat.join(ws)
            try:
                async for msg in ws:
                    await chat.broadcast({"type": "message", "text": msg})
            finally:
                chat.leave(ws)
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._connections: set[WebSocketConnection] = set()

    def join(self, ws: WebSocketConnection) -> None:
        """Add a connection to the room."""
        self._connections.add(ws)
        logger.debug("WebSocketRoom(%s): client joined, total=%d", self.name, self.count)

    def leave(self, ws: WebSocketConnection) -> None:
        """Remove a connection from the room."""
        self._connections.discard(ws)
        logger.debug("WebSocketRoom(%s): client left, total=%d", self.name, self.count)

    @property
    def count(self) -> int:
        """Number of active connections in this room."""
        return len(self._connections)

    async def broadcast(self, data: Any) -> None:
        """Send a JSON-serializable message to all members."""
        stale: list[WebSocketConnection] = []
        for ws in list(self._connections):
            if ws.is_closed:
                stale.append(ws)
                continue
            try:
                await ws.send_json(data)
            except Exception as exc:
                logger.warning("Broadcast failed for a client: %s", exc)
                stale.append(ws)
        for ws in stale:
            self._connections.discard(ws)

    async def broadcast_text(self, text: str) -> None:
        """Send raw text to all members."""
        stale: list[WebSocketConnection] = []
        for ws in list(self._connections):
            if ws.is_closed:
                stale.append(ws)
                continue
            try:
                await ws.send_text(text)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self._connections.discard(ws)

    def __repr__(self) -> str:
        return f"<WebSocketRoom name={self.name!r} connections={self.count}>"
