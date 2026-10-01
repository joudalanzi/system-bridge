"""System identity and the registry that holds adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SystemDefinition:
    """Static metadata for a registered system."""

    system_id: str
    name: str
    enabled: bool = True


class SystemAdapter(ABC):
    """Identity of one external system. Tool calls go through the gateway."""

    @property
    @abstractmethod
    def definition(self) -> SystemDefinition:
        """Return this system's definition."""

    @property
    def system_id(self) -> str:
        return self.definition.system_id

    @property
    def enabled(self) -> bool:
        return self.definition.enabled

    def list_tools(self) -> list[str]:
        """Return tool names owned by this system. Empty until tools are added."""
        return []


class SystemRegistry:
    """In-memory registry of system adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, SystemAdapter] = {}

    def register(self, adapter: SystemAdapter) -> None:
        system_id = adapter.system_id.strip()
        if not system_id:
            raise ValueError("system_id must be a non-empty string")
        if system_id in self._adapters:
            raise ValueError(f"System already registered: {system_id}")
        self._adapters[system_id] = adapter

    def get(self, system_id: str) -> SystemAdapter | None:
        return self._adapters.get(system_id)

    def list_systems(self, *, enabled_only: bool = False) -> list[SystemDefinition]:
        definitions = [adapter.definition for adapter in self._adapters.values()]
        if enabled_only:
            return [item for item in definitions if item.enabled]
        return list(definitions)

    def is_enabled(self, system_id: str) -> bool:
        adapter = self.get(system_id)
        if adapter is None:
            return False
        return adapter.enabled
