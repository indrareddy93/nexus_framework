"""Nexus CLI — project scaffolding and dev server runner."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="nexus",
        description="Nexus Framework CLI — scaffold, run, and manage your Nexus app.",
    )
    sub = parser.add_subparsers(dest="command")

    # nexus create
    create_parser = sub.add_parser("create", help="Scaffold a project or module app")
    create_sub = create_parser.add_subparsers(dest="create_type")

    proj_parser = create_sub.add_parser("project", help="Create a new full Nexus project")
    proj_parser.add_argument("name", help="Project directory name")

    app_parser = create_sub.add_parser("app", help="Generate a CRUD app module inside your project")
    app_parser.add_argument("name", help="App/module name (e.g. users, posts)")

    # nexus run
    run_parser = sub.add_parser("run", help="Start the Nexus dev server")
    run_parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    run_parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    run_parser.add_argument("--reload", action="store_true", default=True, help="Enable auto-reload")
    run_parser.add_argument("--app", default="app:app", help="ASGI app import string (default: app:app)")

    # nexus version
    ver_parser = sub.add_parser("version", help="Print framework version")

    args = parser.parse_args()

    if args.command == "create":
        if args.create_type == "project":
            _create_project(args.name)
        elif args.create_type == "app":
            _create_app(args.name)
        else:
            create_parser.print_help()
    elif args.command == "run":
        _run_server(args.app, args.host, args.port, args.reload)
    elif args.command == "version":
        from nexus import __version__
        print(f"Nexus Framework v{__version__}")
    else:
        parser.print_help()


def _create_project(name: str) -> None:
    base = os.path.abspath(name)
    if os.path.exists(base):
        print(f"❌  Directory '{name}' already exists.")
        sys.exit(1)

    dirs = [
        base,
        os.path.join(base, "apps"),
        os.path.join(base, "config"),
        os.path.join(base, "tests"),
        os.path.join(base, "docs"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    _write(os.path.join(base, "app.py"), textwrap.dedent(f"""\
        \"\"\"
        {name} — powered by Nexus Framework
        \"\"\"\n
        from nexus import Nexus
        from nexus.core.middleware import CORSMiddleware, LoggingMiddleware

        app = Nexus(title="{name} API", version="0.1.0", debug=True)
        app.add_middleware(LoggingMiddleware())
        app.add_middleware(CORSMiddleware(allow_origins=["*"]))


        @app.get("/")
        async def index():
            return {{"status": "ok", "app": "{name}"}}


        @app.on_startup
        async def startup():
            pass  # initialise database, caches, task queues here


        if __name__ == "__main__":
            import uvicorn
            uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
    """))

    _write(os.path.join(base, "config", "settings.yaml"), textwrap.dedent("""\
        debug: true
        database_url: sqlite:///app.db
        secret_key: change-me-in-production
        allowed_hosts:
          - "*"
    """))

    _write(os.path.join(base, "requirements.txt"), textwrap.dedent("""\
        nexus-framework[full]
        uvicorn[standard]>=0.30.0
        httpx>=0.27.0
        pyjwt>=2.8
    """))

    _write(os.path.join(base, "Dockerfile"), textwrap.dedent("""\
        FROM python:3.12-slim
        WORKDIR /app
        COPY requirements.txt .
        RUN pip install --no-cache-dir -r requirements.txt
        COPY . .
        EXPOSE 8000
        CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
    """))

    _write(os.path.join(base, ".env"), textwrap.dedent("""\
        DEBUG=true
        DATABASE_URL=sqlite:///app.db
        SECRET_KEY=change-me-in-production
        # OPENAI_API_KEY=sk-...
    """))

    _write(os.path.join(base, "tests", "__init__.py"), "")
    _write(os.path.join(base, "tests", "test_app.py"), textwrap.dedent("""\
        \"\"\"Basic smoke tests.\"\"\"\n
        import json, pytest
        from app import app

        async def _call(method, path):
            status = {}
            chunks = []
            msgs = [{"body": b"", "more_body": False}]
            async def receive(): return msgs.pop(0) if msgs else {"body": b"", "more_body": False}
            async def send(msg):
                if msg["type"] == "http.response.start": status["code"] = msg["status"]
                elif msg["type"] == "http.response.body": chunks.append(msg.get("body", b""))
            scope = {"type": "http", "method": method, "path": path,
                     "headers": [], "query_string": b""}
            await app(scope, receive, send)
            return status.get("code", 0), json.loads(b"".join(chunks) or b"{}")

        @pytest.mark.asyncio
        async def test_health():
            code, data = await _call("GET", "/")
            assert code == 200
            assert data["status"] == "ok"
    """))

    _write(os.path.join(base, "README.md"), f"# {name}\n\nPowered by [Nexus Framework](https://github.com/indrareddy93/nexus_framework).\n")

    print(f"✅  Created Nexus project '{name}'")
    print(f"\n   cd {name}")
    print("   pip install -r requirements.txt")
    print("   nexus run")


def _create_app(name: str) -> None:
    app_dir = os.path.join("apps", name)
    if not os.path.exists("apps"):
        os.makedirs("apps", exist_ok=True)
    os.makedirs(app_dir, exist_ok=True)

    _write(os.path.join(app_dir, "__init__.py"), "")

    _write(os.path.join(app_dir, "models.py"), textwrap.dedent(f"""\
        from nexus.orm import Model, IntField, StrField, BoolField, DateTimeField

        class {name.capitalize()}(Model):
            __table__ = "{name}s"
            id = IntField(primary_key=True, auto_increment=True)
            name = StrField(max_length=255)
            is_active = BoolField(default=True)
            created_at = DateTimeField(auto_now_add=True)
    """))

    _write(os.path.join(app_dir, "routes.py"), textwrap.dedent(f"""\
        from nexus.core.routing import Router
        from nexus.core.responses import JSONResponse

        router = Router(prefix="/{name}s", tags=["{name}s"])

        @router.get("")
        async def list_{name}s():
            return {{"{name}s": []}}

        @router.get("/{{id}}")
        async def get_{name}(id: int):
            return {{"{name}": None, "id": id}}

        @router.post("")
        async def create_{name}(name: str):
            return {{"{name}": name, "created": True}}
    """))

    _write(os.path.join(app_dir, "services.py"), textwrap.dedent(f"""\
        \"\"\"Business logic for the {name} app.\"\"\"\n
        # Add your service functions here
    """))

    print(f"✅  Created app module 'apps/{name}/'")
    print("\n   Import in your app.py:")
    print(f"   from apps.{name}.routes import router as {name}_router")
    print(f"   app.include_router({name}_router)")


def _run_server(app_str: str, host: str, port: int, reload: bool) -> None:
    cmd = [
        sys.executable, "-m", "uvicorn", app_str,
        "--host", host,
        "--port", str(port),
    ]
    if reload:
        cmd.append("--reload")
    print(f"🚀  Starting Nexus dev server: http://{host}:{port}")
    print(f"   Docs: http://{host}:{port}/docs")
    try:
        subprocess.run(cmd, check=False)
    except KeyboardInterrupt:
        print("\n👋  Server stopped.")


def _write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
