"""Nexus Application — the central ASGI app that wires everything together."""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Callable

from nexus.core.config import Config
from nexus.core.dependencies import DIContainer
from nexus.core.middleware import Middleware
from nexus.core.requests import Request
from nexus.core.responses import JSONResponse, HTMLResponse, Response
from nexus.core.routing import Router, _path_to_regex

logger = logging.getLogger("nexus")


class Nexus:
    """
    The core Nexus application — an ASGI app.

    Usage::

        from nexus import Nexus

        app = Nexus(title="My API")

        @app.get("/")
        async def index():
            return {"message": "Hello, Nexus!"}

    Run with: ``uvicorn myapp:app``
    """

    def __init__(
        self,
        title: str = "Nexus API",
        version: str = "1.0.0",
        description: str = "",
        debug: bool = False,
    ) -> None:
        self.title = title
        self.version = version
        self.description = description
        self.debug = debug

        self.config = Config()
        self.router = Router()
        self.services = DIContainer()
        self._middleware: list[Middleware] = []
        self._on_startup: list[Callable] = []
        self._on_shutdown: list[Callable] = []
        self._exception_handlers: dict[type, Callable] = {}
        self._started = False

    # ── Route decorators (delegate to router) ────────────────────────────────

    def get(self, path: str, **kw: Any) -> Callable:
        return self.router.get(path, **kw)

    def post(self, path: str, **kw: Any) -> Callable:
        return self.router.post(path, **kw)

    def put(self, path: str, **kw: Any) -> Callable:
        return self.router.put(path, **kw)

    def patch(self, path: str, **kw: Any) -> Callable:
        return self.router.patch(path, **kw)

    def delete(self, path: str, **kw: Any) -> Callable:
        return self.router.delete(path, **kw)

    def websocket(self, path: str, **kw: Any) -> Callable:
        return self.router.websocket(path, **kw)

    # ── Sub-routers & modules ─────────────────────────────────────────────────

    def include_router(self, router: Router, prefix: str = "") -> None:
        """Mount another Router's routes into this app."""
        effective_prefix = prefix.rstrip("/")
        for route in router.routes:
            new_path = effective_prefix + route.path
            # Rebuild regex for the new full path
            route.path = new_path
            route.regex = _path_to_regex(new_path)
            self.router.routes.append(route)

    def mount_module(self, module: Any, prefix: str = "") -> None:
        """
        Mount a Nexus module (Django-like app). The module must
        expose a ``router`` attribute.
        """
        if hasattr(module, "router"):
            self.include_router(module.router, prefix=prefix)
        if hasattr(module, "on_startup"):
            self._on_startup.append(module.on_startup)
        if hasattr(module, "on_shutdown"):
            self._on_shutdown.append(module.on_shutdown)

    # ── Middleware ────────────────────────────────────────────────────────────

    def add_middleware(self, mw: Middleware) -> None:
        self._middleware.append(mw)

    # ── Lifecycle hooks ───────────────────────────────────────────────────────

    def on_startup(self, fn: Callable) -> Callable:
        self._on_startup.append(fn)
        return fn

    def on_shutdown(self, fn: Callable) -> Callable:
        self._on_shutdown.append(fn)
        return fn

    def exception_handler(self, exc_type: type) -> Callable:
        def decorator(fn: Callable) -> Callable:
            self._exception_handlers[exc_type] = fn
            return fn

        return decorator

    # ── OpenAPI ───────────────────────────────────────────────────────────────

    def openapi_schema(self) -> dict[str, Any]:
        return {
            "openapi": "3.1.0",
            "info": {
                "title": self.title,
                "version": self.version,
                "description": self.description,
            },
            "paths": self.router.openapi_paths(),
        }

    # ── ASGI interface ────────────────────────────────────────────────────────

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        scope["app"] = self

        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
            return

        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)
            return

    # ── Internal handlers ─────────────────────────────────────────────────────

    async def _handle_lifespan(self, scope: dict, receive: Any, send: Any) -> None:
        while True:
            msg = await receive()
            if msg["type"] == "lifespan.startup":
                try:
                    for fn in self._on_startup:
                        r = fn()
                        if asyncio.iscoroutine(r):
                            await r
                    self._started = True
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    await send({"type": "lifespan.startup.failed", "message": str(exc)})
                    return
            elif msg["type"] == "lifespan.shutdown":
                for fn in self._on_shutdown:
                    r = fn()
                    if asyncio.iscoroutine(r):
                        await r
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def _handle_http(self, scope: dict, receive: Any, send: Any) -> None:
        request = Request(scope, receive)

        # Built-in docs endpoints
        if request.path == "/openapi.json":
            resp = JSONResponse(self.openapi_schema())
            await resp(scope, receive, send)
            return
        if request.path == "/docs":
            resp = self._swagger_ui()
            await resp(scope, receive, send)
            return

        # Run middleware (before)
        for mw in self._middleware:
            short_circuit = await mw.before_request(request)
            if short_circuit is not None:
                resp = self._ensure_response(short_circuit)
                await resp(scope, receive, send)
                return

        # Route resolution
        match = self.router.resolve(request.method, request.path)
        if match is None:
            resp = JSONResponse({"error": "Not Found", "path": request.path}, status_code=404)
            for mw in reversed(self._middleware):
                resp = await mw.after_response(request, resp)
            await self._ensure_response(resp)(scope, receive, send)
            return

        route, path_params = match
        scope["path_params"] = path_params

        try:
            result = await self.services.resolve_handler(
                route.handler,
                path_params=path_params,
                request=request,
            )
            resp = self._ensure_response(result)
        except Exception as exc:
            resp = await self._handle_exception(request, exc)

        # Run middleware (after)
        for mw in reversed(self._middleware):
            resp = await mw.after_response(request, resp)

        resp = self._ensure_response(resp)
        await resp(scope, receive, send)

    async def _handle_websocket(self, scope: dict, receive: Any, send: Any) -> None:
        request = Request(scope, receive)
        match = self.router.resolve("WEBSOCKET", request.path)
        if match is None:
            await send({"type": "websocket.close", "code": 4004})
            return
        route, path_params = match
        scope["path_params"] = path_params

        if asyncio.iscoroutinefunction(route.handler):
            await route.handler(scope, receive, send)
        else:
            route.handler(scope, receive, send)

    async def _handle_exception(self, request: Request, exc: Exception) -> Response:
        for exc_type, handler in self._exception_handlers.items():
            if isinstance(exc, exc_type):
                result = handler(request, exc)
                if asyncio.iscoroutine(result):
                    result = await result
                return self._ensure_response(result)

        logger.exception("Unhandled exception on %s %s", request.method, request.path)
        detail = str(exc) if self.debug else "Internal Server Error"
        body: dict[str, Any] = {"error": detail}
        if self.debug:
            body["traceback"] = traceback.format_exc()
        return JSONResponse(body, status_code=500)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _ensure_response(result: Any) -> Response:
        if result is None:
            return JSONResponse({"detail": "No content"}, status_code=204)
        if isinstance(result, Response):
            return result
        if hasattr(result, "__call__") and hasattr(result, "status_code"):
            return result  # StreamingResponse etc.
        if isinstance(result, (dict, list)):
            return JSONResponse(result)
        if isinstance(result, str):
            return HTMLResponse(result)
        return JSONResponse(result)

    def _swagger_ui(self) -> HTMLResponse:
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{self.title} — API Docs</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
  <style>body{{margin:0;padding:0;}}</style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({{
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
      layout: "BaseLayout",
      deepLinking: true,
    }});
  </script>
</body>
</html>"""
        return HTMLResponse(html)
