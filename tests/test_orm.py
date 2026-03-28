"""Tests for nexus.orm (Model, fields, ModelManager, QueryBuilder)."""

import os
import tempfile
import pytest
from nexus.orm import (
    Model, IntField, StrField, BoolField, JSONField, DateTimeField, ModelManager
)


class SampleUser(Model):
    __table__ = "sample_users"
    id = IntField(primary_key=True, auto_increment=True)
    name = StrField(max_length=100)
    email = StrField(max_length=255, unique=True)
    is_active = BoolField(default=True)
    meta = JSONField(nullable=True)
    created_at = DateTimeField(auto_now_add=True)


def test_create_table_sql():
    sql = SampleUser.create_table_sql()
    assert "CREATE TABLE IF NOT EXISTS sample_users" in sql
    assert "id INTEGER PRIMARY KEY AUTOINCREMENT" in sql
    assert "email VARCHAR(255)" in sql


def test_model_to_dict():
    u = SampleUser(name="Test", email="t@t.com")
    d = u.to_dict()
    assert d["name"] == "Test"
    assert d["email"] == "t@t.com"
    assert "id" in d


def test_model_repr():
    u = SampleUser(name="Alice", email="a@a.com")
    assert "SampleUser" in repr(u)


def test_bool_field_conversion():
    u = SampleUser(name="x", email="x@x.com", is_active=True)
    fld = SampleUser._fields["is_active"]
    assert fld.python_to_db(True) == 1
    assert fld.db_to_python(1) is True
    assert fld.db_to_python(0) is False


def test_json_field_roundtrip():
    fld = JSONField()
    data = {"key": [1, 2, 3]}
    serialized = fld.python_to_db(data)
    assert isinstance(serialized, str)
    assert fld.db_to_python(serialized) == data


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield f"sqlite:///{path}"
    os.unlink(path)


@pytest.mark.asyncio
async def test_orm_full_crud(tmp_db):
    mgr = ModelManager(tmp_db)
    await mgr.connect()
    await mgr.create_tables(SampleUser)

    # Create
    u = SampleUser(name="Alice", email="alice@test.com")
    await mgr.save(u)
    assert u.id is not None

    # Read
    fetched = await mgr.get(SampleUser, u.id)
    assert fetched is not None
    assert fetched.name == "Alice"

    # Query with filter
    await mgr.save(SampleUser(name="Bob", email="bob@test.com", is_active=True))
    await mgr.save(SampleUser(name="Carol", email="carol@test.com", is_active=False))
    active = await mgr.query(SampleUser).filter(is_active=True).all()
    assert len(active) >= 1

    # Count
    cnt = await mgr.query(SampleUser).count()
    assert cnt >= 3

    # JSON field
    u2 = SampleUser(name="Json", email="json@test.com", meta={"x": [1, 2]})
    await mgr.save(u2)
    f2 = await mgr.get(SampleUser, u2.id)
    assert f2.meta == {"x": [1, 2]}

    # Delete
    await mgr.delete(u)
    assert await mgr.get(SampleUser, u.id) is None

    await mgr.close()


@pytest.mark.asyncio
async def test_query_builder(tmp_db):
    mgr = ModelManager(tmp_db)
    await mgr.connect()
    await mgr.create_tables(SampleUser)
    for i in range(10):
        await mgr.save(SampleUser(name=f"User{i}", email=f"u{i}@t.com"))

    page = await mgr.query(SampleUser).order_by("name").limit(3).offset(2).all()
    assert len(page) == 3

    first = await mgr.query(SampleUser).filter(name="User0").first()
    assert first is not None and first.name == "User0"

    cnt = await mgr.query(SampleUser).filter(is_active=True).count()
    assert cnt == 10

    await mgr.close()


@pytest.mark.asyncio
async def test_query_lookup_operators(tmp_db):
    mgr = ModelManager(tmp_db)
    await mgr.connect()
    await mgr.create_tables(SampleUser)
    await mgr.save(SampleUser(name="Alice", email="alice@test.com"))
    await mgr.save(SampleUser(name="Bob", email="bob@test.com"))

    results = await mgr.query(SampleUser).filter(name__in=["Alice", "Bob"]).all()
    assert len(results) == 2

    await mgr.close()
