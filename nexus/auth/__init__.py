"""nexus.auth package — JWT authentication and RBAC."""

from nexus.auth.jwt import JWTAuth, jwt_required
from nexus.auth.rbac import RBAC, Role, require_role

__all__ = [
    "JWTAuth",
    "jwt_required",
    "RBAC",
    "Role",
    "require_role",
]
