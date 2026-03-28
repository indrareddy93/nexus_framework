"""Configuration management — .env, YAML, environment variables."""

from __future__ import annotations

import os
from typing import Any


class Config:
    """
    Layered configuration store.

    Priority (highest → lowest):
        environment variables → load_dict → load_env → load_yaml → defaults

    Usage::

        config = Config(env_prefix="APP_")
        config.load_env(".env")
        config.load_yaml("config.yaml")

        db_url = config.get("DATABASE_URL", "sqlite:///app.db")
    """

    def __init__(self, env_prefix: str = "") -> None:
        self._prefix = env_prefix
        self._data: dict[str, str] = {}

    # ── Loaders ─────────────────────────────────────────────────────────────

    def load_dict(self, mapping: dict[str, Any]) -> None:
        """Override / extend config from a plain dict."""
        for k, v in mapping.items():
            self._data[k] = str(v)

    def load_env(self, path: str = ".env") -> None:
        """Parse a .env file (KEY=value lines, supports quoted values)."""
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                self._data[key] = value

    def load_yaml(self, path: str = "config.yaml") -> None:
        """Parse a YAML config file (requires pyyaml)."""
        if not os.path.exists(path):
            return
        try:
            import yaml  # type: ignore
        except ImportError:
            raise ImportError("Install pyyaml to use load_yaml: pip install pyyaml")
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self.load_dict({k.upper(): v for k, v in data.items()})

    # ── Accessors ────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Return value — checks env vars first (with optional prefix)."""
        env_key = self._prefix + key if self._prefix else key
        env_val = os.environ.get(env_key)
        if env_val is not None:
            return env_val
        return self._data.get(key, default)

    def require(self, key: str) -> str:
        """Like get() but raises if missing."""
        val = self.get(key)
        if val is None:
            raise KeyError(f"Required config key '{key}' is not set.")
        return val

    def get_int(self, key: str, default: int = 0) -> int:
        return int(self.get(key, default))

    def get_bool(self, key: str, default: bool = False) -> bool:
        val = self.get(key, str(default))
        return str(val).lower() in ("1", "true", "yes", "on")

    def __repr__(self) -> str:
        return f"<Config keys={list(self._data.keys())}>"
