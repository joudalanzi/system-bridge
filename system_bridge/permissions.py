"""Authorization contract and a caller-supplied in-memory grant store."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from system_bridge.systems import SystemAdapter, SystemRegistry


class DenyReason(str, Enum):
    SYSTEM_NOT_FOUND = "system_not_found"
    SYSTEM_DISABLED = "system_disabled"
    NO_SYSTEM_ACCESS = "no_system_access"
    MISSING_PERMISSION = "missing_permission"


@dataclass(frozen=True)
class AuthorizationResult:
    allowed: bool
    reason: str | None = None
    detail: str = ""

    @classmethod
    def allow(cls) -> "AuthorizationResult":
        return cls(allowed=True, reason=None, detail="allowed")

    @classmethod
    def deny(cls, reason: DenyReason, detail: str) -> "AuthorizationResult":
        return cls(allowed=False, reason=reason.value, detail=detail)


class PermissionService(ABC):
    """Authorization boundary for system access and permissions."""

    @abstractmethod
    def list_accessible_systems(self, user_id: str) -> list[str]:
        """Return system_ids the user can access (enabled systems only)."""

    @abstractmethod
    def has_system_access(self, user_id: str, system_id: str) -> bool:
        """True if the user may use the system at all."""

    @abstractmethod
    def has_permission(self, user_id: str, system_id: str, permission: str) -> bool:
        """True if the user has a specific permission inside a system."""

    @abstractmethod
    def authorize(
        self,
        user_id: str,
        system_id: str,
        permission: str,
    ) -> AuthorizationResult:
        """Evaluate access for (user, system, permission)."""


class MemoryPermissionService(PermissionService):
    """Grant map supplied by the caller. This store has no built-in grants."""

    def __init__(
        self,
        registry: SystemRegistry,
        grants: dict[str, dict[str, set[str]]] | None = None,
    ) -> None:
        self._registry = registry
        self._grants = {
            user_id: {
                system_id: set(permissions)
                for system_id, permissions in systems.items()
            }
            for user_id, systems in (grants or {}).items()
        }

    def list_accessible_systems(self, user_id: str) -> list[str]:
        return [
            system_id
            for system_id in self._grants.get(user_id, {})
            if self._registry.is_enabled(system_id)
        ]

    def has_system_access(self, user_id: str, system_id: str) -> bool:
        return self._check_system_gate(user_id, system_id).allowed

    def has_permission(self, user_id: str, system_id: str, permission: str) -> bool:
        return self.authorize(user_id, system_id, permission).allowed

    def authorize(
        self,
        user_id: str,
        system_id: str,
        permission: str,
    ) -> AuthorizationResult:
        gate = self._check_system_gate(user_id, system_id)
        if not gate.allowed:
            return gate

        normalized = permission.strip()
        if not normalized:
            return AuthorizationResult.deny(
                DenyReason.MISSING_PERMISSION,
                "Permission name is required",
            )

        user_permissions = self._grants.get(user_id, {}).get(system_id, set())
        if normalized not in user_permissions:
            return AuthorizationResult.deny(
                DenyReason.MISSING_PERMISSION,
                f"Missing permission '{normalized}' on system '{system_id}'",
            )
        return AuthorizationResult.allow()

    def _check_system_gate(self, user_id: str, system_id: str) -> AuthorizationResult:
        adapter: SystemAdapter | None = self._registry.get(system_id)
        if adapter is None:
            return AuthorizationResult.deny(
                DenyReason.SYSTEM_NOT_FOUND,
                f"Unknown system: {system_id}",
            )
        if not adapter.enabled:
            return AuthorizationResult.deny(
                DenyReason.SYSTEM_DISABLED,
                f"System is disabled: {system_id}",
            )
        if system_id not in self._grants.get(user_id, {}):
            return AuthorizationResult.deny(
                DenyReason.NO_SYSTEM_ACCESS,
                f"User has no access to system: {system_id}",
            )
        return AuthorizationResult.allow()
