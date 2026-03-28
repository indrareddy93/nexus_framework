"""Dependency Injection — automatic resolution, scoped lifetimes."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, TypeVar, get_type_hints

T = TypeVar("T")


class Depends:
    """
    Marker for dependency injection.

    Usage::

        async def get_db():
            db = Database()
            try:
                yield db
            finally:
                await db.close()

        @app.get("/items")
        async def list_items(db=Depends(get_db)):
            ...
    """

    def __init__(self, dependency: Callable, *, use_cache: bool = True) -> None:
        self.dependency = dependency
        self.use_cache = use_cache

    def __repr__(self) -> str:
        return f"Depends({self.dependency.__name__})"


class Injectable:
    """
    Base class for injectable services (singleton-style).

    Subclass and register with the DI container::

        class EmailService(Injectable):
            async def send(self, to, body): ...

        app.services.register(EmailService)
    """

    pass


class DIContainer:
    """Resolves dependencies for a handler invocation."""

    def __init__(self) -> None:
        self._singletons: dict[type, Any] = {}
        self._factories: dict[type, Callable] = {}

    def register(self, cls: type[T], factory: Callable[..., T] | None = None) -> None:
        self._factories[cls] = factory or cls

    def register_instance(self, cls: type[T], instance: T) -> None:
        self._singletons[cls] = instance

    async def resolve(self, cls: type[T]) -> T:
        if cls in self._singletons:
            return self._singletons[cls]
        factory = self._factories.get(cls)
        if factory is None:
            raise LookupError(f"No provider registered for {cls}")
        if asyncio.iscoroutinefunction(factory):
            instance = await factory()
        else:
            instance = factory()
        self._singletons[cls] = instance
        return instance

    async def resolve_handler(
        self,
        handler: Callable,
        *,
        path_params: dict[str, str],
        request: Any,
    ) -> Any:
        """Call *handler* with its dependencies resolved automatically."""
        sig = inspect.signature(handler)
        hints = {}
        try:
            hints = get_type_hints(handler)
        except Exception:
            pass

        kwargs: dict[str, Any] = {}
        generators: list = []
        cache: dict = {}

        for name, param in sig.parameters.items():
            # Inject the Request object
            if name == "request":
                kwargs["request"] = request
                continue

            # Depends() marker
            default = param.default
            if isinstance(default, Depends):
                value = await self._resolve_depends(default, request=request, cache=cache)
                if inspect.isasyncgen(value) or inspect.isgenerator(value):
                    generators.append(value)
                kwargs[name] = value
                continue

            # Path parameters (auto-cast)
            if name in path_params:
                ann = hints.get(name, str)
                try:
                    kwargs[name] = ann(path_params[name])
                except (ValueError, TypeError):
                    kwargs[name] = path_params[name]
                continue

            # Query parameters from request
            if request is not None:
                qval = request.query(name)
                if qval is not None:
                    ann = hints.get(name, str)
                    try:
                        kwargs[name] = ann(qval)
                    except (ValueError, TypeError):
                        kwargs[name] = qval
                    continue

            # Body params for POST/PUT/PATCH
            if request is not None and request.method in ("POST", "PUT", "PATCH"):
                try:
                    body = await request.json()
                    if isinstance(body, dict) and name in body:
                        kwargs[name] = body[name]
                        continue
                except Exception:
                    pass

            # Use default if available
            if param.default is not inspect.Parameter.empty and not isinstance(param.default, Depends):
                kwargs[name] = param.default

        # Call the handler
        if asyncio.iscoroutinefunction(handler):
            result = await handler(**kwargs)
        else:
            result = handler(**kwargs)

        # Clean up generator dependencies
        for gen in generators:
            try:
                if inspect.isasyncgen(gen):
                    await gen.__anext__()
                else:
                    next(gen)
            except (StopAsyncIteration, StopIteration):
                pass

        return result

    async def _resolve_depends(
        self, dep: Depends, *, request: Any, cache: dict
    ) -> Any:
        key = id(dep.dependency)
        if dep.use_cache and key in cache:
            return cache[key]

        fn = dep.dependency
        sig = inspect.signature(fn)
        sub_kwargs: dict[str, Any] = {}
        for name, param in sig.parameters.items():
            if name == "request":
                sub_kwargs["request"] = request
            elif isinstance(param.default, Depends):
                sub_kwargs[name] = await self._resolve_depends(
                    param.default, request=request, cache=cache
                )

        if asyncio.iscoroutinefunction(fn):
            value = await fn(**sub_kwargs)
        elif inspect.isasyncgenfunction(fn):
            gen = fn(**sub_kwargs)
            value = await gen.__anext__()
        elif inspect.isgeneratorfunction(fn):
            gen = fn(**sub_kwargs)
            value = next(gen)
        else:
            value = fn(**sub_kwargs)

        if dep.use_cache:
            cache[key] = value
        return value
