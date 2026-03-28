"""JWT Authentication — pure Python HS256, no external deps beyond stdlib."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    # Re-add padding
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


class JWTAuth:
    """
    HS256 JWT token creation and validation — zero external dependencies.

    Usage::

        auth = JWTAuth(secret="super-secret", expiry_seconds=3600)
        token = auth.create_token({"user_id": 1, "role": "admin"})
        payload = auth.decode_token(token)  # None if expired / invalid
    """

    ALGORITHM = "HS256"

    def __init__(self, secret: str, expiry_seconds: int = 3600) -> None:
        self.secret = secret.encode()
        self.expiry_seconds = expiry_seconds

    def create_token(self, payload: dict[str, Any]) -> str:
        """Create a signed JWT with `exp` automatically added."""
        header = {"alg": self.ALGORITHM, "typ": "JWT"}
        now = time.time()
        claims = {
            **payload,
            "iat": int(now),
            "exp": int(now + self.expiry_seconds),
        }
        header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
        payload_b64 = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
        message = f"{header_b64}.{payload_b64}"
        sig = hmac.new(self.secret, message.encode(), hashlib.sha256).digest()
        return f"{message}.{_b64url_encode(sig)}"

    def decode_token(self, token: str) -> Optional[dict[str, Any]]:
        """Verify and decode a JWT. Returns None if invalid or expired."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            header_b64, payload_b64, sig_b64 = parts
            message = f"{header_b64}.{payload_b64}"
            expected_sig = hmac.new(self.secret, message.encode(), hashlib.sha256).digest()
            actual_sig = _b64url_decode(sig_b64)
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None
            claims = json.loads(_b64url_decode(payload_b64))
            if "exp" in claims and time.time() > claims["exp"]:
                return None
            return claims
        except Exception:
            return None


# ── Dependency helper ─────────────────────────────────────────────────────────

from nexus.core.requests import Request


def jwt_required(auth_instance: JWTAuth):
    """
    Dependency factory — injects verified JWT payload or raises 401.

    Usage::

        @app.get("/protected")
        async def protected(payload=Depends(jwt_required(auth))):
            return {"user_id": payload["user_id"]}
    """

    async def _dependency(request: Request) -> dict[str, Any]:
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            raise PermissionError("Missing or invalid Authorization header")
        token = header[7:]
        payload = auth_instance.decode_token(token)
        if payload is None:
            raise PermissionError("Invalid or expired token")
        return payload

    return _dependency
