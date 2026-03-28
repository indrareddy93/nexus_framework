<div align="center">
  <h1>Nexus Framework</h1>
  <p><b>A next-generation Python async web framework.</b></p>
  <p><em>Django completeness, FastAPI performance, Flask simplicity, and AI-native design.</em></p>
</div>

---

Nexus Framework is a modern, zero-dependency (using Python standard library where possible) web framework built from the ground up to solve modern application requirements. It features a complete stack including routing, ORM, dependency injection, caching, background tasks, WebSockets, and natively integrated AI pipelines.

## 🌟 Key Features

* **ASGI-Native Core**: High-performance request/response model built on ASGI.
* **Auto-generated OpenAPI & Swagger UI**: Instantly documented APIs.
* **FastAPI-style Dependency Injection**: Clean, reusable `Depends()` architecture with generator cleanup.
* **Built-in Async ORM**: Chainable query builder, declarative models, JSON fields, and relationship support.
* **JWT & RBAC**: Out-of-the-box pure Python HS256 JWT auth and Role-Based Access Control.
* **Caching & Tasks**: In-memory caching with TTL and an async background task queue with automated retries and backoff.
* **WebSockets**: Simplified pub/sub WebSocket rooms for real-time applications.
* **AI-Native**: Built-in support for OpenAI, Anthropic, Ollama, alongside an in-memory vector store and RAG pipeline.
* **Modular "Django-like" Apps**: Organize complex codebases cleanly with modular routing and CLI scaffolding.

## 🚀 Quickstart

### Installation

```bash
pip install nexus-framework[standard]
```

### Create a Project using the CLI

```bash
nexus create project my_api
cd my_api
nexus run
```

### Manual Setup (`app.py`)

```python
from nexus import Nexus
from nexus.core.responses import JSONResponse

app = Nexus(title="Hello Nexus")

@app.get("/")
async def index():
    return JSONResponse({"status": "ok", "message": "Welcome to Nexus Framework!"})
```

Run the server using Uvicorn:

```bash
uvicorn app:app --reload
```

Then visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to see your automatic Swagger API documentation!

## 📚 Core Modules Guide

### 1. Routing & Dependency Injection

Register routes using decorators and inject dependencies easily:

```python
from nexus import Depends
from nexus.orm.manager import ModelManager

db = ModelManager("sqlite:///app.db")

async def get_db():
    return db

@app.get("/users/{user_id}")
async def get_user(user_id: int, database=Depends(get_db)):
    return {"user_id": user_id}
```

### 2. Async ORM

Define models declaratively and use the chainable query builder:

```python
from nexus.orm import Model, IntField, StrField

class User(Model):
    __table__ = "users"
    id = IntField(primary_key=True, auto_increment=True)
    name = StrField(max_length=255)

# Insert
user = User(name="Alice")
await db.save(user)

# Query
active_users = await db.query(User).filter(name__like="%ice%").order_by("id", desc=True).all()
```

### 3. Authentication & RBAC

Protect your routes out of the box without complex configuration:

```python
from nexus.auth import JWTAuth, jwt_required, require_role

auth = JWTAuth(secret="super-secret")

@app.get("/admin", tags=["admin"])
async def admin_dashboard(
    payload=Depends(jwt_required(auth)),
    _=Depends(require_role("admin"))
):
    return {"data": "Secret admin data"}
```

### 4. Background Tasks

Queue background jobs that automatically retry on failure:

```python
from nexus.tasks import TaskQueue

task_queue = TaskQueue(max_workers=3)

@task_queue.task(retries=3)
async def send_email(to: str):
    # Simulated work
    return {"sent_to": to}

@app.post("/welcome")
async def welcome(email: str):
    await task_queue.enqueue(send_email, email)
    return {"status": "enqueued"}
```

### 5. AI & Embeddings

Build RAG (Retrieval-Augmented Generation) pipelines simply:

```python
from nexus.ai import AIEngine, EmbeddingEngine, RAGPipeline

ai = AIEngine(api_key="sk-your-openai-key")
embeddings = EmbeddingEngine(api_key="sk-your-openai-key")
rag = RAGPipeline(ai, embeddings)

await rag.ingest([{"text": "Nexus supports async architectures."}])
response = await rag.query("What does Nexus support?")
print(response.answer)
```

## 📖 Documentation

For full API references, see the [Reference Guide](docs/REFERENCE.md).
For contributing, see [Contributing](docs/CONTRIBUTING.md).

## 📄 License

MIT License.
