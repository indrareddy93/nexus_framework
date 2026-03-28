"""Async Model Manager — CRUD operations with a query-builder interface."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional, Type, TypeVar

from nexus.orm.base import DateTimeField, Model

T = TypeVar("T", bound=Model)


class AsyncSQLiteConnection:
    """Thin async wrapper around sqlite3 (swap for aiosqlite / asyncpg later)."""

    def __init__(self, database: str) -> None:
        self.database = database
        self._conn: Optional[sqlite3.Connection] = None

    async def connect(self) -> None:
        self._conn = sqlite3.connect(self.database, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    async def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    async def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        assert self._conn is not None, "Not connected — call connect() first"
        cur = self._conn.execute(sql, params)
        self._conn.commit()
        return cur

    async def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        cur = await self.execute(sql, params)
        return cur.fetchall()

    async def fetchone(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        cur = await self.execute(sql, params)
        return cur.fetchone()


class QueryBuilder:
    """Chainable query builder for Model queries."""

    def __init__(self, manager: "ModelManager", model_cls: Type[T]) -> None:
        self._manager = manager
        self._model = model_cls
        self._where: list[str] = []
        self._params: list[Any] = []
        self._order: Optional[str] = None
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None

    def filter(self, **conditions: Any) -> "QueryBuilder":
        """
        Filter by field values. Supports lookup operators via double-underscore::

            .filter(is_active=True)
            .filter(age__gt=18)
            .filter(name__like="%alice%")
            .filter(status__in=["open", "pending"])
        """
        for col, val in conditions.items():
            op = "="
            if "__" in col:
                col, op_name = col.rsplit("__", 1)
                op_map = {
                    "gt": ">",
                    "lt": "<",
                    "gte": ">=",
                    "lte": "<=",
                    "ne": "!=",
                    "like": "LIKE",
                    "ilike": "LIKE",  # SQLite is case-insensitive for ASCII
                    "in": "IN",
                    "notin": "NOT IN",
                }
                op = op_map.get(op_name, "=")
            if op in ("IN", "NOT IN"):
                placeholders = ",".join("?" for _ in val)
                self._where.append(f"{col} {op} ({placeholders})")
                self._params.extend(val)
            else:
                self._where.append(f"{col} {op} ?")
                self._params.append(val)
        return self

    def order_by(self, column: str, desc: bool = False) -> "QueryBuilder":
        direction = "DESC" if desc else "ASC"
        self._order = f"{column} {direction}"
        return self

    def limit(self, n: int) -> "QueryBuilder":
        self._limit = n
        return self

    def offset(self, n: int) -> "QueryBuilder":
        self._offset = n
        return self

    def _build_sql(self) -> tuple[str, tuple]:
        sql = f"SELECT * FROM {self._model.__table__}"
        if self._where:
            sql += " WHERE " + " AND ".join(self._where)
        if self._order:
            sql += f" ORDER BY {self._order}"
        if self._limit is not None:
            sql += f" LIMIT {self._limit}"
        if self._offset is not None:
            sql += f" OFFSET {self._offset}"
        return sql, tuple(self._params)

    async def all(self) -> list[T]:
        sql, params = self._build_sql()
        rows = await self._manager.db.fetchall(sql, params)
        return [self._manager._row_to_model(self._model, row) for row in rows]

    async def first(self) -> Optional[T]:
        self._limit = 1
        results = await self.all()
        return results[0] if results else None

    async def count(self) -> int:
        sql = f"SELECT COUNT(*) as cnt FROM {self._model.__table__}"
        if self._where:
            sql += " WHERE " + " AND ".join(self._where)
        row = await self._manager.db.fetchone(sql, tuple(self._params))
        return row["cnt"] if row else 0

    async def delete(self) -> int:
        sql = f"DELETE FROM {self._model.__table__}"
        if self._where:
            sql += " WHERE " + " AND ".join(self._where)
        cur = await self._manager.db.execute(sql, tuple(self._params))
        return cur.rowcount

    async def update(self, **values: Any) -> int:
        if not values:
            return 0
        set_clause = ", ".join(f"{k} = ?" for k in values)
        params = list(values.values())
        sql = f"UPDATE {self._model.__table__} SET {set_clause}"
        if self._where:
            sql += " WHERE " + " AND ".join(self._where)
            params.extend(self._params)
        cur = await self._manager.db.execute(sql, tuple(params))
        return cur.rowcount


class ModelManager:
    """
    Manages database operations for Model classes.

    Usage::

        db = ModelManager("sqlite:///app.db")
        await db.connect()
        await db.create_tables(User, Post)

        user = User(name="Alice", email="alice@example.com")
        await db.save(user)

        users = await db.query(User).filter(is_active=True).all()
    """

    def __init__(self, database_url: str = "sqlite:///nexus.db") -> None:
        self.database_url = database_url
        db_path = database_url.replace("sqlite:///", "")
        self.db = AsyncSQLiteConnection(db_path)

    async def connect(self) -> None:
        await self.db.connect()

    async def close(self) -> None:
        await self.db.close()

    async def create_tables(self, *models: Type[Model]) -> None:
        for model in models:
            await self.db.execute(model.create_table_sql())

    async def drop_tables(self, *models: Type[Model]) -> None:
        for model in models:
            await self.db.execute(f"DROP TABLE IF EXISTS {model.__table__}")

    # ── CRUD ─────────────────────────────────────────────────────────────────

    async def save(self, instance: Model) -> Model:
        """Insert or update (upsert) a model instance."""
        fields = instance._fields
        pk_name = next((n for n, f in fields.items() if f.primary_key), None)

        # Handle auto timestamps
        for name, fld in fields.items():
            if isinstance(fld, DateTimeField) and fld.auto_now:
                setattr(instance, name, datetime.now(timezone.utc).replace(tzinfo=None))

        cols = []
        vals = []
        for name, fld in fields.items():
            val = getattr(instance, name, None)
            if fld.primary_key and val is None:
                continue  # let auto-increment handle it
            cols.append(name)
            vals.append(fld.python_to_db(val))

        placeholders = ",".join("?" for _ in cols)
        sql = f"INSERT OR REPLACE INTO {instance.__table__} ({','.join(cols)}) VALUES ({placeholders})"
        cur = await self.db.execute(sql, tuple(vals))

        if pk_name and getattr(instance, pk_name, None) is None:
            setattr(instance, pk_name, cur.lastrowid)

        return instance

    async def get(self, model: Type[T], pk: Any) -> Optional[T]:
        pk_name = next((n for n, f in model._fields.items() if f.primary_key), "id")
        row = await self.db.fetchone(
            f"SELECT * FROM {model.__table__} WHERE {pk_name} = ?", (pk,)
        )
        return self._row_to_model(model, row) if row else None

    async def delete(self, instance: Model) -> None:
        pk_name = next((n for n, f in instance._fields.items() if f.primary_key), "id")
        pk_val = getattr(instance, pk_name)
        await self.db.execute(
            f"DELETE FROM {instance.__table__} WHERE {pk_name} = ?", (pk_val,)
        )

    async def bulk_create(self, instances: list[Model]) -> list[Model]:
        """Insert multiple instances efficiently."""
        for instance in instances:
            await self.save(instance)
        return instances

    def query(self, model: Type[T]) -> QueryBuilder:
        return QueryBuilder(self, model)

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_model(model: Type[T], row: Any) -> T:
        data = dict(row)
        for name, fld in model._fields.items():
            if name in data:
                data[name] = fld.db_to_python(data[name])
        return model(**data)
