"""Integration tests — full ASGI request/response cycle."""

import json
import pytest
from nexus import Nexus, Router


def _make_app() -> Nexus:
    a = Nexus(title="Test", debug=True)

    @a.get("/")
    async def index():
        return {"ok": True}

    @a.get("/users/{uid}")
    async def get_user(uid: int):
        return {"uid": uid}

    @a.post("/echo")
    async def echo(message: str):
        return {"echo": message}

    return a


async def _call(app, method, path, body=None, headers=None):
    body_bytes = json.dumps(body).encode() if body else b""
    h = [(b"content-type", b"application/json")]
    if headers:
        h.extend((k.encode(), v.encode()) for k, v in headers.items())
    msgs = [{"body": body_bytes, "more_body": False}]
    status = {}
    chunks = []

    async def receive():
        return msgs.pop(0) if msgs else {"body": b"", "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            status["code"] = msg["status"]
        elif msg["type"] == "http.response.body":
            chunks.append(msg.get("body", b""))

    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": h,
        "query_string": b"",
    }
    await app(scope, receive, send)
    data = json.loads(b"".join(chunks)) if chunks else {}
    return status.get("code", 0), data


@pytest.mark.asyncio
async def test_health_check():
    code, data = await _call(_make_app(), "GET", "/")
    assert code == 200
    assert data["ok"] is True


@pytest.mark.asyncio
async def test_path_param_injection():
    code, data = await _call(_make_app(), "GET", "/users/42")
    assert code == 200
    assert data["uid"] == 42


@pytest.mark.asyncio
async def test_404_not_found():
    code, _ = await _call(_make_app(), "GET", "/nope")
    assert code == 404


@pytest.mark.asyncio
async def test_openapi_schema():
    code, data = await _call(_make_app(), "GET", "/openapi.json")
    assert code == 200
    assert data["openapi"] == "3.1.0"
    assert "/" in data["paths"]


@pytest.mark.asyncio
async def test_swagger_ui():
    app = _make_app()
    status = {}
    chunks = []
    msgs = [{"body": b"", "more_body": False}]

    async def receive():
        return msgs.pop(0) if msgs else {"body": b"", "more_body": False}

    async def send(msg):
        if msg["type"] == "http.response.start":
            status["code"] = msg["status"]
        elif msg["type"] == "http.response.body":
            chunks.append(msg.get("body", b""))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/docs",
        "headers": [],
        "query_string": b"",
    }
    await app(scope, receive, send)
    assert status["code"] == 200
    html = b"".join(chunks).decode()
    assert "swagger-ui" in html


@pytest.mark.asyncio
async def test_include_router():
    app = Nexus(title="Test")
    router = Router(prefix="/api")

    @router.get("/items")
    async def items():
        return {"items": []}

    app.include_router(router)
    code, data = await _call(app, "GET", "/api/items")
    assert code == 200
    assert "items" in data


@pytest.mark.asyncio
async def test_middleware_cors():
    from nexus.core.middleware import CORSMiddleware
    app = _make_app()
    app.add_middleware(CORSMiddleware(allow_origins=["*"]))
    code, data = await _call(app, "GET", "/")
    assert code == 200


@pytest.mark.asyncio
async def test_di_path_params():
    from nexus.core.dependencies import Depends, DIContainer
    c = DIContainer()

    async def get_multiplier():
        return 10

    async def handler(user_id: int, mult=Depends(get_multiplier)):
        return user_id * mult

    result = await c.resolve_handler(
        handler, path_params={"user_id": "5"}, request=None
    )
    assert result == 50


@pytest.mark.asyncio
async def test_exception_handler():
    app = Nexus(debug=True)

    @app.get("/boom")
    async def boom():
        raise ValueError("test error")

    code, data = await _call(app, "GET", "/boom")
    assert code == 500
    assert "error" in data
