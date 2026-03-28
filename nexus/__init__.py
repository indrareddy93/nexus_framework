"""
Nexus Framework
===============

A next-generation async Python web framework.

  - ASGI-native with decorator routing and auto OpenAPI/Swagger
  - FastAPI-style dependency injection
  - Async ORM with chainable query builder
  - JWT auth + RBAC
  - In-memory cache with TTL and @cached decorator
  - Background task queue with retry
  - WebSocket pub/sub rooms
  - AI-native: LLM engine, embeddings, RAG pipeline
  - CLI scaffolding

Quick start::

    from nexus import Nexus

    app = Nexus(title="My API")

    @app.get("/")
    async def index():
        return {"status": "ok"}

Run::

    uvicorn app:app --reload
"""

from nexus.core.app import Nexus
from nexus.core.config import Config
from nexus.core.dependencies import Depends, DIContainer, Injectable
from nexus.core.middleware import (
    CORSMiddleware,
    GZipMiddleware,
    LoggingMiddleware,
    Middleware,
    RateLimitMiddleware,
)
from nexus.core.requests import Request
from nexus.core.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from nexus.core.routing import Router

__version__ = "0.1.0"
__author__ = "Nexus Contributors"

__all__ = [
    # Core
    "Nexus",
    "Router",
    "Request",
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "RedirectResponse",
    "StreamingResponse",
    # DI
    "Depends",
    "DIContainer",
    "Injectable",
    # Config
    "Config",
    # Middleware
    "Middleware",
    "CORSMiddleware",
    "LoggingMiddleware",
    "RateLimitMiddleware",
    "GZipMiddleware",
    # Version
    "__version__",
]
