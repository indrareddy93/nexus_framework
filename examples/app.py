"""
Example Nexus Application
==========================

Demonstrates: routing, DI, ORM, auth, caching, background tasks,
WebSockets, AI integration, modular apps, and middleware.

Run:  uvicorn examples.app:app --reload
Docs: http://127.0.0.1:8000/docs
"""

import asyncio
import logging
from nexus import Nexus, Router, Depends, Request, JSONResponse, StreamingResponse
from nexus.core.middleware import CORSMiddleware, LoggingMiddleware, RateLimitMiddleware
from nexus.orm import Model, IntField, StrField, BoolField, JSONField, DateTimeField
from nexus.orm.manager import ModelManager
from nexus.auth import JWTAuth, jwt_required, RBAC, Role
from nexus.cache import InMemoryCache
from nexus.cache.backend import cached
from nexus.tasks import TaskQueue
from nexus.websocket import WebSocketConnection, WebSocketRoom

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")

# ═══════════════════════════════════════════════════════════════════════════
# 1. APP SETUP
# ═══════════════════════════════════════════════════════════════════════════

app = Nexus(title="Nexus Example API", version="0.1.0", debug=True)

# Middleware stack
app.add_middleware(LoggingMiddleware())
app.add_middleware(CORSMiddleware(allow_origins=["*"]))
app.add_middleware(RateLimitMiddleware(requests_per_minute=120))

# Services
db = ModelManager("sqlite:///example.db")
auth = JWTAuth(secret="nexus-demo-secret-key", expiry_seconds=7200)
cache = InMemoryCache(default_ttl=300)
task_queue = TaskQueue(max_workers=5)
chat_room = WebSocketRoom("general")

# RBAC
rbac = RBAC()
rbac.add_role(Role("admin", {"read", "write", "delete", "manage"}))
rbac.add_role(Role("editor", {"read", "write"}))
rbac.add_role(Role("viewer", {"read"}))


# ═══════════════════════════════════════════════════════════════════════════
# 2. MODELS
# ═══════════════════════════════════════════════════════════════════════════

class User(Model):
    __table__ = "users"
    id = IntField(primary_key=True, auto_increment=True)
    username = StrField(max_length=100, unique=True)
    email = StrField(max_length=255, unique=True)
    role = StrField(max_length=50, default="viewer")
    is_active = BoolField(default=True)
    meta = JSONField(nullable=True)
    created_at = DateTimeField(auto_now_add=True)


class Post(Model):
    __table__ = "posts"
    id = IntField(primary_key=True, auto_increment=True)
    title = StrField(max_length=500)
    body = StrField(max_length=50000)
    author_id = IntField()
    tags = JSONField(default=[])
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)


# ═══════════════════════════════════════════════════════════════════════════
# 3. DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════

async def get_db():
    """Dependency: database session."""
    return db

async def get_current_user(request: Request):
    """Dependency: extract user from JWT."""
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        return None
    payload = auth.decode_token(header[7:])
    if payload and "user_id" in payload:
        return await db.get(User, payload["user_id"])
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 4. LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════

@app.on_startup
async def startup():
    await db.connect()
    await db.create_tables(User, Post)
    await task_queue.start()
    logging.info("🚀 Nexus example app started")

@app.on_shutdown
async def shutdown():
    await task_queue.stop()
    await db.close()

@app.exception_handler(PermissionError)
async def permission_error_handler(request: Request, exc: PermissionError):
    return JSONResponse({"error": "Forbidden", "detail": str(exc)}, status_code=403)


# ═══════════════════════════════════════════════════════════════════════════
# 5. CORE ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/")
async def index():
    """Health check."""
    return {
        "status": "ok",
        "framework": "Nexus",
        "version": app.version,
        "docs": "/docs",
    }

@app.get("/hello/{name}", tags=["demo"])
async def hello(name: str):
    """Greet someone by name."""
    return {"message": f"Hello, {name}! Welcome to Nexus."}


# ═══════════════════════════════════════════════════════════════════════════
# 6. AUTH ROUTES
# ═══════════════════════════════════════════════════════════════════════════

auth_router = Router(prefix="/auth", tags=["auth"])

@auth_router.post("/register")
async def register(username: str, email: str, role: str = "viewer"):
    """Register a new user."""
    existing = await db.query(User).filter(username=username).first()
    if existing:
        return JSONResponse({"error": "Username taken"}, status_code=409)
    user = User(username=username, email=email, role=role)
    await db.save(user)
    token = auth.create_token({"user_id": user.id, "role": user.role})
    return {"user": user.to_dict(), "token": token}

@auth_router.post("/login")
async def login(username: str):
    """Login (demo — no password check)."""
    user = await db.query(User).filter(username=username).first()
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)
    token = auth.create_token({"user_id": user.id, "role": user.role})
    return {"token": token, "user": user.to_dict()}

@auth_router.get("/me")
async def me(request: Request):
    """Get the current user from JWT."""
    user = await get_current_user(request)
    if not user:
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return {"user": user.to_dict()}

app.include_router(auth_router)


# ═══════════════════════════════════════════════════════════════════════════
# 7. CRUD ROUTES (USERS & POSTS)
# ═══════════════════════════════════════════════════════════════════════════

users_router = Router(prefix="/api/users", tags=["users"])

@users_router.get("")
@cached(cache, ttl=30)
async def list_users():
    """List all active users (cached 30s)."""
    users = await db.query(User).filter(is_active=True).all()
    return {"users": [u.to_dict() for u in users]}

@users_router.get("/{user_id}")
async def get_user(user_id: int):
    """Get a user by ID."""
    user = await db.get(User, user_id)
    if not user:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {"user": user.to_dict()}

@users_router.delete("/{user_id}")
async def delete_user(user_id: int, request: Request):
    """Delete a user (admin only)."""
    current = await get_current_user(request)
    if not current or current.role != "admin":
        return JSONResponse({"error": "Admin access required"}, status_code=403)
    user = await db.get(User, user_id)
    if user:
        await db.delete(user)
    return {"deleted": True}

app.include_router(users_router)


posts_router = Router(prefix="/api/posts", tags=["posts"])

@posts_router.get("")
async def list_posts():
    """List all posts (newest first)."""
    posts = await db.query(Post).order_by("created_at", desc=True).limit(50).all()
    return {"posts": [p.to_dict() for p in posts]}

@posts_router.post("")
async def create_post(title: str, body: str, request: Request):
    """Create a new post."""
    user = await get_current_user(request)
    author_id = user.id if user else 0
    post = Post(title=title, body=body, author_id=author_id)
    await db.save(post)
    return {"post": post.to_dict(), "created": True}

@posts_router.get("/{post_id}")
async def get_post(post_id: int):
    """Get a post by ID."""
    post = await db.get(Post, post_id)
    if not post:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {"post": post.to_dict()}

app.include_router(posts_router)


# ═══════════════════════════════════════════════════════════════════════════
# 8. BACKGROUND TASKS
# ═══════════════════════════════════════════════════════════════════════════

@task_queue.task(retries=3)
async def send_welcome_email(user_id: int):
    """Simulated email task."""
    await asyncio.sleep(0.1)
    logging.info(f"Welcome email sent to user {user_id}")
    return {"sent_to": user_id}

@app.post("/api/tasks/welcome", tags=["tasks"])
async def enqueue_welcome(user_id: int):
    """Enqueue a welcome email task."""
    task_id = await task_queue.enqueue(send_welcome_email, user_id)
    return {"task_id": task_id, "status": "enqueued"}

@app.get("/api/tasks/{task_id}", tags=["tasks"])
async def get_task_status(task_id: str):
    """Check task status by ID."""
    task = task_queue.get_task(task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return {
        "id": task.id,
        "name": task.name,
        "status": task.status.value,
        "result": task.result,
        "attempts": task.attempts,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 9. CACHING DEMO
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/cache/stats", tags=["cache"])
async def cache_stats():
    """View cache statistics."""
    return {"cached_items": cache.size()}


# ═══════════════════════════════════════════════════════════════════════════
# 10. WEBSOCKET (CHAT)
# ═══════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/chat")
async def websocket_chat(scope, receive, send):
    """Real-time chat over WebSocket."""
    ws = WebSocketConnection(scope, receive, send)
    await ws.accept()
    chat_room.join(ws)
    try:
        async for message in ws:
            await chat_room.broadcast({"type": "message", "text": message})
    except Exception:
        pass
    finally:
        chat_room.leave(ws)

@app.get("/api/chat/stats", tags=["websocket"])
async def chat_stats():
    """WebSocket room statistics."""
    return {"room": chat_room.name, "connected_clients": chat_room.count}


# ═══════════════════════════════════════════════════════════════════════════
# 11. AI ROUTES (requires API key)
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/ai/chat", tags=["ai"])
async def ai_chat(message: str):
    """
    AI chat endpoint (demo).
    Set OPENAI_API_KEY env var to enable real AI responses.
    """
    import os
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return {
            "response": f"[AI demo] You said: '{message}'. Set OPENAI_API_KEY for real responses.",
            "model": "demo",
        }
    from nexus.ai import AIEngine
    ai = AIEngine(provider="openai", model="gpt-4o-mini", api_key=api_key)
    result = await ai.generate(message)
    return {"response": result.content, "model": result.model, "usage": result.usage}


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("examples.app:app", host="127.0.0.1", port=8000, reload=True)
