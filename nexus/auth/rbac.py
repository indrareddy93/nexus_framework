"""RBAC — Role-Based Access Control."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Set

from nexus.core.requests import Request


@dataclass
class Role:
    """A named role with a set of permission strings."""

    name: str
    permissions: Set[str] = field(default_factory=set)

    def has_permission(self, perm: str) -> bool:
        return perm in self.permissions or "*" in self.permissions


class RBAC:
    """
    Role-Based Access Control manager.

    Usage::

        rbac = RBAC()
        rbac.add_role(Role("admin", {"read", "write", "delete", "manage"}))
        rbac.add_role(Role("editor", {"read", "write"}))
        rbac.add_role(Role("viewer", {"read"}))

        rbac.has_permission("admin", "delete")  # True
        rbac.has_permission("viewer", "delete") # False
    """

    def __init__(self) -> None:
        self._roles: dict[str, Role] = {}
        self._role_hierarchy: dict[str, list[str]] = {}  # parent → children

    def add_role(self, role: Role) -> None:
        self._roles[role.name] = role

    def get_role(self, name: str) -> Role | None:
        return self._roles.get(name)

    def has_permission(self, role_name: str, permission: str) -> bool:
        """Check if a named role has the given permission."""
        role = self._roles.get(role_name)
        if role is None:
            return False
        return role.has_permission(permission)

    def add_inheritance(self, child: str, parent: str) -> None:
        """Grant child role all permissions of parent role."""
        self._role_hierarchy.setdefault(child, []).append(parent)

    def all_permissions(self, role_name: str) -> set[str]:
        """Collect all permissions including inherited ones."""
        perms: set[str] = set()
        role = self._roles.get(role_name)
        if role:
            perms.update(role.permissions)
        for parent in self._role_hierarchy.get(role_name, []):
            perms.update(self.all_permissions(parent))
        return perms


def require_role(*allowed_roles: str) -> Callable:
    """
    Dependency factory that checks the user's role from JWT payload.

    Usage::

        @app.delete("/items/{id}")
        async def delete_item(item_id: int, _=Depends(require_role("admin"))):
            ...
    """

    async def _check(request: Request) -> None:
        # Extract from the Authorization header directly
        from nexus.auth.jwt import JWTAuth  # noqa
        payload = getattr(request, "_jwt_payload", None)
        if payload is None:
            raise PermissionError(f"Role {' or '.join(allowed_roles)} required")
        user_role = payload.get("role", "")
        if user_role not in allowed_roles:
            raise PermissionError(
                f"Role '{user_role}' does not have access. Required: {allowed_roles}"
            )

    return _check
