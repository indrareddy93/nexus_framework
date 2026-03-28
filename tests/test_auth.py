"""Tests for nexus.auth (JWTAuth, RBAC)."""

import time
import pytest
from nexus.auth import JWTAuth, RBAC, Role


def test_jwt_roundtrip():
    auth = JWTAuth(secret="test-secret", expiry_seconds=3600)
    token = auth.create_token({"user_id": 1, "role": "admin"})
    payload = auth.decode_token(token)
    assert payload is not None
    assert payload["user_id"] == 1
    assert payload["role"] == "admin"


def test_jwt_expiry():
    auth = JWTAuth(secret="test-secret", expiry_seconds=0)
    token = auth.create_token({"user_id": 1})
    time.sleep(1)
    assert auth.decode_token(token) is None


def test_jwt_tampered():
    auth = JWTAuth(secret="test-secret")
    token = auth.create_token({"user_id": 1})
    tampered = token[:-5] + "ZZZZZ"
    assert auth.decode_token(tampered) is None


def test_jwt_wrong_secret():
    auth1 = JWTAuth(secret="secret1")
    auth2 = JWTAuth(secret="secret2")
    token = auth1.create_token({"user_id": 1})
    assert auth2.decode_token(token) is None


def test_jwt_malformed():
    auth = JWTAuth(secret="test")
    assert auth.decode_token("not.a.valid.token.at.all") is None
    assert auth.decode_token("") is None
    assert auth.decode_token("only.two") is None


def test_rbac_basic():
    rbac = RBAC()
    rbac.add_role(Role("admin", {"read", "write", "delete"}))
    rbac.add_role(Role("viewer", {"read"}))

    assert rbac.has_permission("admin", "delete") is True
    assert rbac.has_permission("viewer", "delete") is False
    assert rbac.has_permission("viewer", "read") is True
    assert rbac.has_permission("ghost", "read") is False


def test_rbac_wildcard():
    rbac = RBAC()
    rbac.add_role(Role("superadmin", {"*"}))
    assert rbac.has_permission("superadmin", "anything") is True


def test_rbac_get_role():
    rbac = RBAC()
    rbac.add_role(Role("editor", {"read", "write"}))
    role = rbac.get_role("editor")
    assert role is not None
    assert role.name == "editor"
    assert rbac.get_role("nonexistent") is None


def test_rbac_all_permissions():
    rbac = RBAC()
    rbac.add_role(Role("base", {"read"}))
    rbac.add_role(Role("editor", {"write"}))
    rbac.add_inheritance("editor", "base")
    perms = rbac.all_permissions("editor")
    assert "read" in perms
    assert "write" in perms
