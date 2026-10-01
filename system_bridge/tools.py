"""Tool contract and the registry that binds tools to systems."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from system_bridge.systems import SystemRegistry


@dataclass(frozen=True)
class ToolDefinition:
    """Metadata for a system-scoped tool."""

    name: str
    system_id: str
    required_permission: str
    description: str


@dataclass(frozen=True)
class ToolResult:
    """Structured result from a tool run."""

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    error_code: str | None = None


class Tool(ABC):
    """
    Tool bound to one system and one required permission.

    Callers go through ToolGateway so authorization runs before _execute.
    """

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Return this tool's definition."""

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def system_id(self) -> str:
        return self.definition.system_id

    @property
    def required_permission(self) -> str:
        return self.definition.required_permission

    @property
    def retries_transient(self) -> bool:
        """Reads may retry. Mutations override this so a committed write is not sent twice."""
        return True

    @abstractmethod
    def _execute(self, arguments: dict[str, Any]) -> ToolResult:
        """
        Internal execution contract.

        Implementations must not perform authorization themselves.
        ToolGateway is responsible for auth before calling this.
        """


class ToolRegistry:
    """Registry of tools bound to systems in the SystemRegistry."""

    def __init__(self, system_registry: SystemRegistry) -> None:
        self._system_registry = system_registry
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        definition = tool.definition
        name = definition.name.strip()
        system_id = definition.system_id.strip()
        permission = definition.required_permission.strip()

        if not name:
            raise ValueError("tool name must be a non-empty string")
        if not system_id:
            raise ValueError("tool system_id must be a non-empty string")
        if not permission:
            raise ValueError("tool required_permission must be a non-empty string")
        if self._system_registry.get(system_id) is None:
            raise ValueError(f"Cannot register tool for unknown system: {system_id}")
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")

        self._tools[name] = tool

    def get(self, tool_name: str) -> Tool | None:
        return self._tools.get(tool_name)

    def list_tools(self) -> list[ToolDefinition]:
        return [tool.definition for tool in self._tools.values()]

    def list_tools_for_system(self, system_id: str) -> list[ToolDefinition]:
        return [
            tool.definition
            for tool in self._tools.values()
            if tool.system_id == system_id
        ]
