"""Routing — decorator-based, async-first, with OpenAPI generation."""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Callable, get_type_hints


# Convert "/users/{user_id}" → regex with named groups
_PARAM_RE = re.compile(r"\{(\w+)\}")


def _path_to_regex(path: str) -> re.Pattern:
    pattern = _PARAM_RE.sub(r"(?P<\1>[^/]+)", path)
    return re.compile(f"^{pattern}$")


@dataclass
class Route:
    """A single registered route."""

    path: str
    method: str
    handler: Callable
    name: str
    summary: str
    tags: list[str]
    dependencies: list[Any]
    regex: re.Pattern = field(init=False)

    def __post_init__(self) -> None:
        self.regex = _path_to_regex(self.path)

    def match(self, path: str) -> dict[str, str] | None:
        m = self.regex.match(path)
        return m.groupdict() if m else None


class Router:
    """
    Flask/FastAPI-style router with decorator registration.

    Usage::

        router = Router(prefix="/api", tags=["users"])

        @router.get("/users/{user_id}")
        async def get_user(user_id: int):
            ...
    """

    def __init__(
        self,
        prefix: str = "",
        tags: list[str] | None = None,
        dependencies: list[Any] | None = None,
    ) -> None:
        self.prefix = prefix.rstrip("/")
        self.tags = tags or []
        self.dependencies = dependencies or []
        self.routes: list[Route] = []

    # ── Decorator helpers ────────────────────────────────────────────────────

    def route(
        self,
        path: str,
        method: str = "GET",
        *,
        name: str | None = None,
        summary: str = "",
        tags: list[str] | None = None,
        dependencies: list[Any] | None = None,
    ) -> Callable:
        def decorator(fn: Callable) -> Callable:
            full_path = self.prefix + path
            r = Route(
                path=full_path,
                method=method.upper(),
                handler=fn,
                name=name or fn.__name__,
                summary=summary or (fn.__doc__ or "").strip(),
                tags=tags or self.tags,
                dependencies=(self.dependencies + (dependencies or [])),
            )
            self.routes.append(r)
            return fn

        return decorator

    def get(self, path: str, **kw: Any) -> Callable:
        return self.route(path, "GET", **kw)

    def post(self, path: str, **kw: Any) -> Callable:
        return self.route(path, "POST", **kw)

    def put(self, path: str, **kw: Any) -> Callable:
        return self.route(path, "PUT", **kw)

    def patch(self, path: str, **kw: Any) -> Callable:
        return self.route(path, "PATCH", **kw)

    def delete(self, path: str, **kw: Any) -> Callable:
        return self.route(path, "DELETE", **kw)

    def websocket(self, path: str, **kw: Any) -> Callable:
        return self.route(path, "WEBSOCKET", **kw)

    # ── Resolution ──────────────────────────────────────────────────────────

    def resolve(self, method: str, path: str) -> tuple[Route, dict[str, str]] | None:
        for route in self.routes:
            if route.method != method.upper():
                continue
            params = route.match(path)
            if params is not None:
                return route, params
        return None

    # ── OpenAPI generation ───────────────────────────────────────────────────

    def openapi_paths(self) -> dict[str, Any]:
        """Generate OpenAPI paths object for registered routes."""
        paths: dict[str, Any] = {}
        for route in self.routes:
            if route.method == "WEBSOCKET":
                continue
            path_key = _PARAM_RE.sub(r"{\1}", route.path)
            method_key = route.method.lower()

            hints = {}
            try:
                hints = get_type_hints(route.handler)
            except Exception:
                pass
            sig = inspect.signature(route.handler)

            parameters = []
            request_body = None
            path_param_names = _PARAM_RE.findall(route.path)

            for pname, param in sig.parameters.items():
                if pname in ("self", "request"):
                    continue
                ann = hints.get(pname, str)
                type_str = _python_type_to_openapi(ann)

                if pname in path_param_names:
                    parameters.append(
                        {"name": pname, "in": "path", "required": True, "schema": {"type": type_str}}
                    )
                elif route.method in ("POST", "PUT", "PATCH"):
                    if request_body is None:
                        request_body = {
                            "content": {
                                "application/json": {"schema": {"type": "object", "properties": {}}}
                            }
                        }
                    request_body["content"]["application/json"]["schema"]["properties"][pname] = {
                        "type": type_str
                    }
                else:
                    parameters.append(
                        {
                            "name": pname,
                            "in": "query",
                            "required": param.default is inspect.Parameter.empty,
                            "schema": {"type": type_str},
                        }
                    )

            op: dict[str, Any] = {
                "summary": route.summary,
                "operationId": route.name,
                "tags": route.tags,
                "responses": {"200": {"description": "Successful response"}},
            }
            if parameters:
                op["parameters"] = parameters
            if request_body:
                op["requestBody"] = request_body

            paths.setdefault(path_key, {})[method_key] = op
        return paths


def _python_type_to_openapi(t: Any) -> str:
    mapping = {int: "integer", float: "number", bool: "boolean", str: "string"}
    return mapping.get(t, "string")
