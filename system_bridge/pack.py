"""Adapter contract. A system joins the bridge by implementing SystemPack."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from system_bridge.reliability import ReliabilityConfig
from system_bridge.systems import SystemAdapter
from system_bridge.tools import ToolRegistry


class SystemPack(ABC):
    """One external system: its identity and the tools it contributes."""

    @abstractmethod
    def adapter(self) -> SystemAdapter:
        """System id and display name."""

    def reliability(self) -> ReliabilityConfig | None:
        """Timeout policy for this pack, or None to keep the caller default."""
        return None

    def contribute_tools(self, registry: ToolRegistry) -> None:
        """Register this system's tools."""
        return None

    def tool_install_options(self) -> dict[str, Any]:
        """Optional installer options. Empty by default."""
        return {}
