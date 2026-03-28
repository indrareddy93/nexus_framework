"""Manual test runner — runs all tests without pytest."""

import asyncio
import json
import os
import sys
import tempfile
import time
import traceback

sys.path.insert(0, os.path.dirname(__file__))

passed = 0
failed = 0
errors = []


def run_test(name, fn):
    global passed, failed
    try:
        result = fn()
        if asyncio.iscoroutine(result):
            asyncio.get_event_loop().run_until_complete(result)
        passed += 1
        print(f"  ✓ {name}")
    except Exception as e:
        failed += 1
        errors.append((name, e))
        print(f"  ✗ {name}: {e}")


# ── Routing ──────────────────────────────────────────────────────────────────

from nexus.core.routing import Router

print("\n🔀 Routing")

def test_route_registration():
    r = Router()
    @r.get("/items")
    async def list_items(): return []
    assert len(r.routes) == 1
    assert r.routes[0].method == "GET"
run_test("route registration", test_route_registration)

def test_path_params():
    r = Router()
    @r.get("/users/{user_id}")
    async def get_user(user_id: int): pass
    match = r.resolve("GET", "/users/42")
    assert match is not None
    route, params = match
    assert params == {"user_id": "42"}
run_test("path params", test_path_params)

def test_no_match():
    r = Router()
    @r.get("/items")
    async def items(): pass
    assert r.resolve("GET", "/nope") is None
    assert r.resolve("POST", "/items") is None
run_test("no match", test_no_match)

def test_prefix():
    r = Router(prefix="/api/v1")
    @r.get("/users")
    async def users(): pass
    assert r.resolve("GET", "/api/v1/users") is not None
run_test("prefix routing", test_prefix)

def test_openapi():
    r = Router()
    @r.get("/users/{user_id}")
    async def get_user(user_id: int):
        """Get a user."""
    paths = r.openapi_paths()
    assert "/users/{user_id}" in paths
    assert "get" in paths["/users/{user_id}"]
    assert paths["/users/{user_id}"]["get"]["parameters"][0]["name"] == "user_id"
run_test("openapi generation", test_openapi)


# ── Request ──────────────────────────────────────────────────────────────────

from nexus.core.requests import Request

print("\n📥 Request")

def test_request_props():
    scope = {
        "type": "http", "method": "POST", "path": "/test",
        "query_string": b"page=2&limit=10",
        "headers": [(b"content-type", b"application/json")],
    }
    req = Request(scope, None)
    assert req.method == "POST"
    assert req.path == "/test"
    assert req.query("page") == "2"
    assert req.query("missing", "x") == "x"
    assert req.headers["content-type"] == "application/json"
run_test("request properties", test_request_props)

async def test_request_body():
    body = json.dumps({"name": "test"}).encode()
    msgs = [{"body": body, "more_body": False}]
    async def receive(): return msgs.pop(0)
    req = Request({"type": "http", "method": "POST", "path": "/"}, receive)
    data = await req.json()
    assert data == {"name": "test"}
run_test("request body parsing", test_request_body)


# ── Response ─────────────────────────────────────────────────────────────────

from nexus.core.responses import JSONResponse, HTMLResponse, Response

print("\n📤 Response")

def test_json_response():
    r = JSONResponse({"key": "value"}, status_code=201)
    assert r.status_code == 201
    assert json.loads(r.body) == {"key": "value"}
run_test("json response", test_json_response)

def test_html_response():
    r = HTMLResponse("<h1>Hi</h1>")
    assert b"<h1>Hi</h1>" in r.body
run_test("html response", test_html_response)


# ── DI ───────────────────────────────────────────────────────────────────────

from nexus.core.dependencies import Depends, DIContainer

print("\n💉 Dependency Injection")

async def test_basic_di():
    c = DIContainer()
    async def get_val(): return 42
    async def handler(val=Depends(get_val)): return val
    result = await c.resolve_handler(handler, path_params={}, request=None)
    assert result == 42
run_test("basic dependency", test_basic_di)

async def test_path_injection():
    c = DIContainer()
    async def handler(user_id: int): return user_id
    result = await c.resolve_handler(handler, path_params={"user_id": "7"}, request=None)
    assert result == 7
run_test("path param injection", test_path_injection)

async def test_nested_di():
    c = DIContainer()
    async def get_config(): return {"url": "sqlite:///x"}
    async def get_db(config=Depends(get_config)): return f"db:{config['url']}"
    async def handler(db=Depends(get_db)): return db
    result = await c.resolve_handler(handler, path_params={}, request=None)
    assert "sqlite:///x" in result
run_test("nested dependencies", test_nested_di)

async def test_service_register():
    c = DIContainer()
    class Svc:
        def go(self): return "ok"
    c.register(Svc)
    s = await c.resolve(Svc)
    assert s.go() == "ok"
run_test("service registration", test_service_register)


# ── ORM ──────────────────────────────────────────────────────────────────────

from nexus.orm import Model, IntField, StrField, BoolField, JSONField, DateTimeField
from nexus.orm.manager import ModelManager

print("\n🗄️  ORM")

class TestUser(Model):
    __table__ = "test_users"
    id = IntField(primary_key=True, auto_increment=True)
    name = StrField(max_length=100)
    email = StrField(max_length=255, unique=True)
    is_active = BoolField(default=True)
    meta = JSONField(nullable=True)
    created_at = DateTimeField(auto_now_add=True)

def test_create_table_sql():
    sql = TestUser.create_table_sql()
    assert "CREATE TABLE IF NOT EXISTS test_users" in sql
    assert "id INTEGER PRIMARY KEY AUTOINCREMENT" in sql
run_test("create table SQL", test_create_table_sql)

def test_model_dict():
    u = TestUser(name="Test", email="t@t.com")
    d = u.to_dict()
    assert d["name"] == "Test"
    assert "id" in d
run_test("model to_dict", test_model_dict)

async def test_orm_crud():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        mgr = ModelManager(f"sqlite:///{db_path}")
        await mgr.connect()
        await mgr.create_tables(TestUser)

        # Create
        u = TestUser(name="Alice", email="alice@test.com")
        await mgr.save(u)
        assert u.id is not None

        # Read
        fetched = await mgr.get(TestUser, u.id)
        assert fetched.name == "Alice"

        # Query
        await mgr.save(TestUser(name="Bob", email="bob@test.com", is_active=True))
        await mgr.save(TestUser(name="Carol", email="carol@test.com", is_active=False))
        active = await mgr.query(TestUser).filter(is_active=True).all()
        assert len(active) >= 1

        # Count
        cnt = await mgr.query(TestUser).count()
        assert cnt >= 3

        # JSON field
        u2 = TestUser(name="Json", email="json@test.com", meta={"x": [1, 2]})
        await mgr.save(u2)
        f2 = await mgr.get(TestUser, u2.id)
        assert f2.meta == {"x": [1, 2]}

        # Delete
        await mgr.delete(u)
        assert await mgr.get(TestUser, u.id) is None

        await mgr.close()
    finally:
        os.unlink(db_path)
run_test("full CRUD cycle", test_orm_crud)

async def test_query_builder():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        mgr = ModelManager(f"sqlite:///{db_path}")
        await mgr.connect()
        await mgr.create_tables(TestUser)
        for i in range(10):
            await mgr.save(TestUser(name=f"User{i}", email=f"u{i}@t.com"))
        
        page = await mgr.query(TestUser).order_by("name").limit(3).offset(2).all()
        assert len(page) == 3

        first = await mgr.query(TestUser).filter(name="User0").first()
        assert first is not None and first.name == "User0"

        await mgr.close()
    finally:
        os.unlink(db_path)
run_test("query builder (order/limit/offset/first)", test_query_builder)


# ── Auth ─────────────────────────────────────────────────────────────────────

from nexus.auth import JWTAuth, RBAC, Role

print("\n🔐 Auth")

def test_jwt():
    auth = JWTAuth(secret="test", expiry_seconds=3600)
    token = auth.create_token({"user_id": 1, "role": "admin"})
    p = auth.decode_token(token)
    assert p["user_id"] == 1 and p["role"] == "admin"
run_test("JWT roundtrip", test_jwt)

def test_jwt_expired():
    auth = JWTAuth(secret="test", expiry_seconds=0)
    token = auth.create_token({"user_id": 1})
    time.sleep(1)
    assert auth.decode_token(token) is None
run_test("JWT expiry", test_jwt_expired)

def test_jwt_tampered():
    auth = JWTAuth(secret="test")
    token = auth.create_token({"user_id": 1})
    assert auth.decode_token(token[:-5] + "ZZZZZ") is None
run_test("JWT tamper detection", test_jwt_tampered)

def test_rbac():
    rbac = RBAC()
    rbac.add_role(Role("admin", {"read", "write", "delete"}))
    rbac.add_role(Role("viewer", {"read"}))
    assert rbac.has_permission("admin", "delete")
    assert not rbac.has_permission("viewer", "delete")
    assert rbac.has_permission("viewer", "read")
    assert not rbac.has_permission("ghost", "read")
run_test("RBAC permissions", test_rbac)


# ── Cache ────────────────────────────────────────────────────────────────────

from nexus.cache import InMemoryCache

print("\n💾 Cache")

async def test_cache_basic():
    c = InMemoryCache(default_ttl=60)
    await c.set("k", "v")
    assert await c.get("k") == "v"
    await c.delete("k")
    assert await c.get("k") is None
run_test("set/get/delete", test_cache_basic)

async def test_cache_ttl():
    c = InMemoryCache()
    await c.set("k", "v", ttl=0)
    await asyncio.sleep(0.01)
    assert await c.get("k") is None
run_test("TTL expiry", test_cache_ttl)

async def test_get_or_set():
    c = InMemoryCache()
    r = await c.get_or_set("x", lambda: 99)
    assert r == 99
    r2 = await c.get_or_set("x", lambda: 0)
    assert r2 == 99  # cached
run_test("get_or_set", test_get_or_set)


# ── Tasks ────────────────────────────────────────────────────────────────────

from nexus.tasks import TaskQueue
from nexus.tasks.queue import TaskStatus

print("\n⏳ Tasks")

async def test_task_queue():
    q = TaskQueue(max_workers=2)
    @q.task(retries=1)
    async def add(a, b): return a + b
    await q.start()
    tid = await q.enqueue(add, 3, 4)
    await asyncio.sleep(0.5)
    t = q.get_task(tid)
    assert t.status == TaskStatus.COMPLETED
    assert t.result == 7
    await q.stop()
run_test("enqueue & process", test_task_queue)

async def test_task_retry():
    q = TaskQueue(max_workers=1)
    count = 0
    @q.task(retries=3)
    async def flaky():
        nonlocal count; count += 1
        if count < 3: raise ValueError("not yet")
        return "ok"
    await q.start()
    tid = await q.enqueue(flaky)
    await asyncio.sleep(4)
    t = q.get_task(tid)
    assert t.status == TaskStatus.COMPLETED
    assert count == 3
    await q.stop()
run_test("retry on failure", test_task_retry)


# ── Config ───────────────────────────────────────────────────────────────────

from nexus.core.config import Config

print("\n⚙️  Config")

def test_config_dict():
    c = Config()
    c.load_dict({"DB": "sqlite:///x", "DEBUG": "1"})
    assert c.get("DB") == "sqlite:///x"
    assert c.get("NOPE", "default") == "default"
run_test("dict config", test_config_dict)

def test_config_env_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write('KEY="hello"\nOTHER=world\n')
        f.flush()
        c = Config()
        c.load_env(f.name)
        assert c.get("KEY") == "hello"
        assert c.get("OTHER") == "world"
    os.unlink(f.name)
run_test("env file parsing", test_config_env_file)


# ── Middleware ───────────────────────────────────────────────────────────────

from nexus.core.middleware import CORSMiddleware, RateLimitMiddleware

print("\n🛡️  Middleware")

async def test_cors():
    mw = CORSMiddleware(allow_origins=["https://example.com"])
    scope = {"type": "http", "method": "OPTIONS", "path": "/",
             "headers": [(b"origin", b"https://example.com")]}
    req = Request(scope, None)
    resp = await mw.before_request(req)
    assert resp is not None and resp.status_code == 204
run_test("CORS preflight", test_cors)

async def test_rate_limit():
    mw = RateLimitMiddleware(requests_per_minute=2)
    scope = {"type": "http", "method": "GET", "path": "/",
             "headers": [], "client": ("127.0.0.1", 8000)}
    req = Request(scope, None)
    assert await mw.before_request(req) is None
    assert await mw.before_request(req) is None
    resp = await mw.before_request(req)
    assert resp is not None and resp.status_code == 429
run_test("rate limiting", test_rate_limit)


# ── Integration ──────────────────────────────────────────────────────────────

from nexus.core.app import Nexus

print("\n🔗 Integration")

def _make_app():
    a = Nexus(title="Test", debug=True)
    @a.get("/")
    async def index(): return {"ok": True}
    @a.get("/users/{uid}")
    async def get_user(uid: int): return {"uid": uid}
    return a

async def _call(app, method, path, body=None):
    body_bytes = json.dumps(body).encode() if body else b""
    msgs = [{"body": body_bytes, "more_body": False}]
    status = {}
    chunks = []
    async def receive(): return msgs.pop(0) if msgs else {"body": b"", "more_body": False}
    async def send(msg):
        if msg["type"] == "http.response.start": status["code"] = msg["status"]
        elif msg["type"] == "http.response.body": chunks.append(msg.get("body", b""))
    scope = {"type": "http", "method": method, "path": path, "headers": [], "query_string": b""}
    await app(scope, receive, send)
    data = json.loads(b"".join(chunks)) if chunks else {}
    return status.get("code", 0), data

async def test_integration_health():
    code, data = await _call(_make_app(), "GET", "/")
    assert code == 200 and data["ok"] is True
run_test("GET / → 200", test_integration_health)

async def test_integration_path_param():
    code, data = await _call(_make_app(), "GET", "/users/42")
    assert code == 200 and data["uid"] == 42
run_test("GET /users/42 → uid=42", test_integration_path_param)

async def test_integration_404():
    code, _ = await _call(_make_app(), "GET", "/nope")
    assert code == 404
run_test("GET /nope → 404", test_integration_404)

async def test_integration_openapi():
    code, data = await _call(_make_app(), "GET", "/openapi.json")
    assert code == 200
    assert data["openapi"] == "3.1.0"
    assert "/" in data["paths"]
run_test("GET /openapi.json", test_integration_openapi)

async def test_integration_docs():
    app = _make_app()
    body_bytes = b""
    msgs = [{"body": b"", "more_body": False}]
    chunks = []
    status = {}
    async def receive(): return msgs.pop(0) if msgs else {"body": b"", "more_body": False}
    async def send(msg):
        if msg["type"] == "http.response.start": status["code"] = msg["status"]
        elif msg["type"] == "http.response.body": chunks.append(msg.get("body", b""))
    scope = {"type": "http", "method": "GET", "path": "/docs", "headers": [], "query_string": b""}
    await app(scope, receive, send)
    assert status["code"] == 200
    html = b"".join(chunks).decode()
    assert "swagger-ui" in html
run_test("GET /docs → Swagger UI", test_integration_docs)


# ── Summary ──────────────────────────────────────────────────────────────────

print(f"\n{'='*60}")
print(f"  Results: {passed} passed, {failed} failed")
print(f"{'='*60}")

if errors:
    print("\nFailures:")
    for name, exc in errors:
        print(f"\n  {name}:")
        traceback.print_exception(type(exc), exc, exc.__traceback__)

sys.exit(1 if failed else 0)
