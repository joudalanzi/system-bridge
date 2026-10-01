"""system-bridge registers external systems behind one tool gateway.

Distribution name: system-bridge
Import name: system_bridge
"""

__distribution_name__ = "system-bridge"
__version__ = "0.1.0"

from system_bridge.contracts import (
    CapabilityAction,
    DomainDefinition,
    DomainRegistry,
    OperationKind,
    Readiness,
    ToolContract,
)
from system_bridge.gateway import ToolExecutionResult, ToolGateway
from system_bridge.pack import SystemPack
from system_bridge.permissions import (
    AuthorizationResult,
    DenyReason,
    MemoryPermissionService,
    PermissionService,
)
from system_bridge.reliability import ReliabilityConfig
from system_bridge.runtime import BridgeRuntime, build_runtime
from system_bridge.systems import SystemAdapter, SystemDefinition, SystemRegistry
from system_bridge.tools import Tool, ToolDefinition, ToolRegistry, ToolResult

__all__ = [
    "AuthorizationResult",
    "BridgeRuntime",
    "CapabilityAction",
    "DenyReason",
    "DomainDefinition",
    "DomainRegistry",
    "MemoryPermissionService",
    "OperationKind",
    "PermissionService",
    "Readiness",
    "ReliabilityConfig",
    "SystemAdapter",
    "SystemDefinition",
    "SystemPack",
    "SystemRegistry",
    "Tool",
    "ToolContract",
    "ToolDefinition",
    "ToolExecutionResult",
    "ToolGateway",
    "ToolRegistry",
    "ToolResult",
    "__distribution_name__",
    "__version__",
    "build_runtime",
]
