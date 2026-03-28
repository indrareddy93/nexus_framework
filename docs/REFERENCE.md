# Nexus API Reference

This document provides a reference for the core components of the Nexus Framework.

## Core Setup

### `Nexus` (from `nexus.core.app`)
The main ASGI application instance.
*   `__init__(title, version, description, debug)`
*   `get(path)`, `post(path)`, etc.: Route decorators.
*   `websocket(path)`: WebSocket route decorator.
*   `add_middleware(Middleware)`: Mount middleware to the application stack.
*   `include_router(Router, prefix)`: Mount modular routers.
*   `on_startup(Callable)` / `on_shutdown(Callable)`: Lifespan hooks.
*   `exception_handler(ExceptionType)`: Custom exception handling.

### `Router` (from `nexus.core.routing`)
Allows for separation of routes into modular "apps".
*   `__init__(prefix, tags, dependencies)`
*   `get(path, name, summary, tags, dependencies)`, etc.: Works identically to the app routing decorators.

### `Depends` and `DIContainer` (from `nexus.core.dependencies`)
Dependency Injection.
*   `Depends(callable, use_cache=True)`: Marker for injecting dependencies into request handlers.
*   Resolves nested dependencies and runs generator `finally` blocks upon response completion.

### `Middleware` (from `nexus.core.middleware`)
Extend the request pipeline.
*   `CORSMiddleware`
*   `RateLimitMiddleware(requests_per_minute)`
*   `LoggingMiddleware`
*   `TrustedHostMiddleware(allowed_hosts)`
*   `GZipMiddleware(minimum_size)`

---

## Data & Persistence

### `Model` (from `nexus.orm.base`)
Base class for declarative database models.
*   Available fields: `IntField`, `StrField`, `FloatField`, `BoolField`, `JSONField`, `DateTimeField`.
*   Pass constraints into fields: `primary_key`, `auto_increment`, `nullable`, `unique`, `default`.

### `ModelManager` (from `nexus.orm.manager`)
Async SQLite (or compatible) wrapper for schema creation and CRUD.
*   `connect()` / `close()`
*   `create_tables(*models)`
*   `save(instance)`: Inserts or updates a model.
*   `get(Model, id)`: Fetches a single record by PK.
*   `delete(instance)`
*   `query(Model)`: Retuns a `QueryBuilder`.

### `QueryBuilder`
Chainable syntax to fetch data.
*   `filter(**kwargs)`: e.g., `.filter(name="Alice", age__gt=18, status__in=["active", "pending"])`
*   `order_by(column, desc=False)`
*   `limit(n)`, `offset(n)`
*   `all()`: returns `list[Model]`
*   `first()`: returns `Model | None`
*   `count()`: returns `int`

---

## Features

### Authentication (`nexus.auth`)
*   `JWTAuth(secret, expiry_seconds)`: Generate and decode tokens.
*   `jwt_required(JWTAuth)`: A `Depends()` factory that enforces a valid token.
*   `RBAC`: Role-Based Access Control allowing inheritance structure.
*   `require_role(*roles)`: A `Depends()` factory forcing a specific role in the JWT payload.

### Background Tasks (`nexus.tasks`)
*   `TaskQueue(max_workers)`: Instantiates the worker queue.
*   `@task_queue.task(retries=N)`: Decorator to register a function.
*   `enqueue(fn, *args, **kwargs)` / `enqueue_in(delay, fn, *args, **kwargs)`
*   `get_task(task_id)` / `list_tasks()`: Poll execution status.

### Caching (`nexus.cache`)
*   `InMemoryCache(default_ttl)`
*   `get(key)`, `set(key, value, ttl)`, `delete(key)`
*   `get_or_set(key, factory)`
*   `@cached(cache_instance, ttl)`: Decorator for auto-caching handler outputs.

### AI engine (`nexus.ai`)
*   `AIEngine(provider, model, api_key)`: Unified generation (OpenAI, Anthropic, Ollama, Groq).
*   `EmbeddingEngine`: Generates vectors via API or local fallback, providing `search()`.
*   `RAGPipeline`: Integrates AIEngine and EmbeddingEngine for one-liner `.ingest()` and `.query()` contextual generation.
