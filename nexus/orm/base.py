"""ORM base — Model class, field descriptors, table DDL."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


# ── Field descriptors ────────────────────────────────────────────────────────


class Field:
    """Base field descriptor."""

    def __init__(
        self,
        column_type: str = "TEXT",
        *,
        primary_key: bool = False,
        nullable: bool = True,
        default: Any = None,
        unique: bool = False,
        index: bool = False,
    ) -> None:
        self.column_type = column_type
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.unique = unique
        self.index = index

    def to_sql_type(self) -> str:
        parts = [self.column_type]
        if self.primary_key:
            parts.append("PRIMARY KEY")
        if not self.nullable and not self.primary_key:
            parts.append("NOT NULL")
        if self.unique and not self.primary_key:
            parts.append("UNIQUE")
        return " ".join(parts)

    def python_to_db(self, value: Any) -> Any:
        return value

    def db_to_python(self, value: Any) -> Any:
        return value


class IntField(Field):
    def __init__(self, *, primary_key: bool = False, auto_increment: bool = False, **kw: Any) -> None:
        super().__init__("INTEGER", primary_key=primary_key, **kw)
        self.auto_increment = auto_increment

    def to_sql_type(self) -> str:
        base = super().to_sql_type()
        if self.auto_increment:
            base = base.replace("PRIMARY KEY", "PRIMARY KEY AUTOINCREMENT")
        return base


class StrField(Field):
    def __init__(self, max_length: int = 255, **kw: Any) -> None:
        super().__init__(f"VARCHAR({max_length})", **kw)
        self.max_length = max_length


class FloatField(Field):
    def __init__(self, **kw: Any) -> None:
        super().__init__("REAL", **kw)


class BoolField(Field):
    def __init__(self, **kw: Any) -> None:
        super().__init__("BOOLEAN", **kw)

    def python_to_db(self, value: Any) -> Any:
        return int(value) if value is not None else None

    def db_to_python(self, value: Any) -> Any:
        return bool(value) if value is not None else None


class JSONField(Field):
    def __init__(self, **kw: Any) -> None:
        super().__init__("TEXT", **kw)

    def python_to_db(self, value: Any) -> Any:
        return json.dumps(value) if value is not None else None

    def db_to_python(self, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return value
        return value


class DateTimeField(Field):
    def __init__(self, auto_now: bool = False, auto_now_add: bool = False, **kw: Any) -> None:
        super().__init__("TIMESTAMP", **kw)
        self.auto_now = auto_now
        self.auto_now_add = auto_now_add

    def python_to_db(self, value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def db_to_python(self, value: Any) -> Any:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return value
        return value


# ── Model metaclass ──────────────────────────────────────────────────────────


class ModelMeta(type):
    """Metaclass that collects Field descriptors into _fields."""

    def __new__(mcs, name: str, bases: tuple, namespace: dict) -> "ModelMeta":
        fields: dict[str, Field] = {}
        # Inherit fields from base classes
        for base in bases:
            if hasattr(base, "_fields"):
                fields.update(base._fields)
        for key, val in list(namespace.items()):
            if isinstance(val, Field):
                fields[key] = val
        namespace["_fields"] = fields
        namespace.setdefault("__table__", name.lower() + "s")
        cls = super().__new__(mcs, name, bases, namespace)
        return cls


class Model(metaclass=ModelMeta):
    """
    Base model — declare fields as class attributes.

    Usage::

        class User(Model):
            __table__ = "users"
            id = IntField(primary_key=True, auto_increment=True)
            name = StrField(max_length=100)
            email = StrField(max_length=255, unique=True)
            is_active = BoolField(default=True)
            meta = JSONField(nullable=True)
            created_at = DateTimeField(auto_now_add=True)
    """

    _fields: dict[str, Field]
    __table__: str

    def __init__(self, **kwargs: Any) -> None:
        for name, fld in self._fields.items():
            value = kwargs.get(name, fld.default)
            if isinstance(fld, DateTimeField) and fld.auto_now_add and value is None:
                value = datetime.now(timezone.utc).replace(tzinfo=None)
            setattr(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for name in self._fields:
            val = getattr(self, name, None)
            if isinstance(val, datetime):
                result[name] = val.isoformat()
            else:
                result[name] = val
        return result

    @classmethod
    def create_table_sql(cls) -> str:
        cols = []
        for name, fld in cls._fields.items():
            cols.append(f"  {name} {fld.to_sql_type()}")
        return f"CREATE TABLE IF NOT EXISTS {cls.__table__} (\n" + ",\n".join(cols) + "\n);"

    def __repr__(self) -> str:
        pk = next((n for n, f in self._fields.items() if f.primary_key), None)
        pk_val = getattr(self, pk, "?") if pk else "?"
        return f"<{self.__class__.__name__} {pk}={pk_val}>"
