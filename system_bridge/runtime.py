"""Assemble a runtime from the packs the caller supplies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from system_bridge.gateway import SessionGrant, ToolGateway
from system_bridge.pack import SystemPack
from system_bridge.permissions import MemoryPermissionService, PermissionService
from system_bridge.reliability import ReliabilityConfig
from system_bridge.systems import SystemRegistry
from system_bridge.tools import Tool, ToolRegistry

PermissionFactory = Callable[[SystemRegistry], PermissionService]


class _PackScopedRegistry:
    """A pack may register tools only for the system it owns."""

    def __init__(self, inner: ToolRegistry, system_id: str) -> None:
        self._inner = inner
        self._system_id = system_id

    def register(self, tool: Tool) -> None:
        owned = tool.definition.system_id.strip()
        if owned != self._system_id:
            raise ValueError(
                f"Pack '{self._system_id}' cannot register a tool for system '{owned}'"
            )
        self._inner.register(tool)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


@dataclass
class BridgeRuntime:
    """Systems, tools, permissions, and the single gateway."""

    systems: SystemRegistry
    tools: ToolRegistry
    permissions: PermissionService
    gateway: ToolGateway
    domains: Any = None


def build_runtime(
    packs: list[SystemPack] | None = None,
    extra_packs: list[SystemPack] | None = None,
    *,
    grants: dict[str, dict[str, set[str]]] | None = None,
    permission_service: PermissionService | None = None,
    permission_factory: PermissionFactory | None = None,
    domain_registry: Any = None,
    reliability: ReliabilityConfig | None = None,
    session_grant: SessionGrant | None = None,
    gateway_cls: type[ToolGateway] | None = None,
) -> BridgeRuntime:
    """Register each pack, then build one gateway over their tools.

    ``packs`` and ``extra_packs`` are the same list. An empty call registers
    no business system. Grants, contracts, and the gateway class come from
    the caller. This function does not load a built-in product.
    """
    systems = SystemRegistry()
    loaded = list(packs or []) + list(extra_packs or [])
    prepared: list[tuple[SystemPack, str]] = []
    chosen_reliability = reliability
    for pack in loaded:
        adapter = pack.adapter()
        systems.register(adapter)
        prepared.append((pack, adapter.definition.system_id.strip()))
        if chosen_reliability is None:
            pack_reliability = pack.reliability()
            if pack_reliability is not None:
                chosen_reliability = pack_reliability

    if permission_service is not None:
        permissions = permission_service
    elif permission_factory is not None:
        permissions = permission_factory(systems)
    else:
        permissions = MemoryPermissionService(systems, grants or {})
    tools = ToolRegistry(systems)
    for pack, system_id in prepared:
        pack.contribute_tools(_PackScopedRegistry(tools, system_id))

    gateway_type = gateway_cls or ToolGateway
    gateway = gateway_type(
        tools,
        permissions,
        reliability=chosen_reliability,
        domain_registry=domain_registry,
        session_grant=session_grant,
    )
    return BridgeRuntime(
        systems=systems,
        tools=tools,
        permissions=permissions,
        domains=domain_registry,
        gateway=gateway,
    )
