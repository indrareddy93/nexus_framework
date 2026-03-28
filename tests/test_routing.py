"""Tests for nexus.core.routing."""

import pytest
from nexus.core.routing import Router, _path_to_regex


def test_route_registration():
    r = Router()

    @r.get("/items")
    async def list_items():
        return []

    assert len(r.routes) == 1
    assert r.routes[0].method == "GET"
    assert r.routes[0].path == "/items"


def test_path_params():
    r = Router()

    @r.get("/users/{user_id}")
    async def get_user(user_id: int):
        pass

    match = r.resolve("GET", "/users/42")
    assert match is not None
    route, params = match
    assert params == {"user_id": "42"}


def test_no_match():
    r = Router()

    @r.get("/items")
    async def items():
        pass

    assert r.resolve("GET", "/nope") is None
    assert r.resolve("POST", "/items") is None


def test_prefix_routing():
    r = Router(prefix="/api/v1")

    @r.get("/users")
    async def users():
        pass

    assert r.resolve("GET", "/api/v1/users") is not None
    assert r.resolve("GET", "/users") is None


def test_multi_method():
    r = Router()

    @r.get("/x")
    async def get_x():
        pass

    @r.post("/x")
    async def post_x():
        pass

    assert r.resolve("GET", "/x") is not None
    assert r.resolve("POST", "/x") is not None
    assert r.resolve("DELETE", "/x") is None


def test_websocket_route():
    r = Router()

    @r.websocket("/ws")
    async def ws_handler(scope, receive, send):
        pass

    assert r.resolve("WEBSOCKET", "/ws") is not None


def test_openapi_paths():
    r = Router()

    @r.get("/users/{user_id}")
    async def get_user(user_id: int):
        """Get a user."""

    paths = r.openapi_paths()
    assert "/users/{user_id}" in paths
    assert "get" in paths["/users/{user_id}"]
    params = paths["/users/{user_id}"]["get"]["parameters"]
    assert params[0]["name"] == "user_id"
    assert params[0]["in"] == "path"


def test_tags_inherit():
    r = Router(tags=["widgets"])

    @r.get("/widgets")
    async def list_widgets():
        pass

    route = r.routes[0]
    assert "widgets" in route.tags


def test_path_to_regex():
    pattern = _path_to_regex("/users/{user_id}/posts/{post_id}")
    m = pattern.match("/users/42/posts/99")
    assert m is not None
    assert m.groupdict() == {"user_id": "42", "post_id": "99"}
