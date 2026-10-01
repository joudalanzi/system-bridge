"""Generic domain and tool contracts. The host fills in the catalog."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum


class Readiness(str, Enum):
    """Whether a domain or tool may run."""

    IMPLEMENTED = "implemented"
    PLANNED = "planned"
    NOT_READY = "not_ready"
    FORBIDDEN = "forbidden"


class OperationKind(str, Enum):
    """Operation class. These are not transport verbs."""

    READ = "read"
    WRITE = "write"
    WORKFLOW = "workflow"
    DESTRUCTIVE = "destructive"


class CapabilityAction(str, Enum):
    """Capability verb. DELETE is never executable."""

    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    COMPLETE = "complete"
    DELETE = "delete"
    ASSIST = "assist"


@dataclass(frozen=True)
class DomainDefinition:
    """One functional area inside a system."""

    system_id: str
    domain_id: str
    display_name: str
    readiness: Readiness
    description: str = ""
    display_name_ar: str = ""
    display_name_en: str = ""
    parent_domain_id: str | None = None
    known_endpoints: tuple[str, ...] = ()
    naming_notes: str = ""


@dataclass(frozen=True)
class ToolContract:
    """Metadata the gateway reads before it allows a tool to run."""

    tool_name: str
    system_id: str
    domain_id: str
    capability: str
    operation: OperationKind
    status: Readiness
    authz_permission: str
    adapter: str
    required_arguments: tuple[str, ...] = ()
    result_schema_ref: str = ""
    confirmation_required: bool = False
    description: str = ""
    notes: str = ""
    action: CapabilityAction | None = None
    disabled_reason: str = ""

    @property
    def is_executable(self) -> bool:
        return self.status == Readiness.IMPLEMENTED

    @property
    def is_forbidden(self) -> bool:
        if self.status == Readiness.FORBIDDEN:
            return True
        if self.operation == OperationKind.DESTRUCTIVE:
            return True
        if self.action == CapabilityAction.DELETE:
            return True
        return False

    @property
    def capability_action(self) -> CapabilityAction:
        if self.action is not None:
            return self.action
        if self.operation == OperationKind.READ:
            return CapabilityAction.READ
        if self.operation == OperationKind.DESTRUCTIVE:
            return CapabilityAction.DELETE
        if self.operation == OperationKind.WORKFLOW:
            return CapabilityAction.COMPLETE
        return CapabilityAction.CREATE


@dataclass(frozen=True)
class DomainMappingRow:
    """Flat display row for a domain. Metadata only."""

    system_id: str
    technical_domain: str
    display_name_ar: str
    display_name_en: str
    parent_domain: str | None
    status: Readiness
    capabilities: tuple[str, ...] = ()
    known_endpoints: tuple[str, ...] = ()
    naming_notes: str = ""


class DomainRegistry:
    """System, domain, and tool-contract catalog. It does not grant permissions."""

    def __init__(self) -> None:
        self._domains: dict[tuple[str, str], DomainDefinition] = {}
        self._contracts_by_tool: dict[str, ToolContract] = {}
        self._contracts: list[ToolContract] = []

    def register_domain(self, domain: DomainDefinition) -> None:
        key = (domain.system_id, domain.domain_id)
        if key in self._domains:
            raise ValueError(
                f"Domain already registered: {domain.system_id}/{domain.domain_id}"
            )
        self._domains[key] = domain

    def register_contract(self, contract: ToolContract) -> None:
        if (
            contract.is_executable
            and not contract.is_forbidden
            and contract.capability_action
            in {
                CapabilityAction.CREATE,
                CapabilityAction.UPDATE,
                CapabilityAction.COMPLETE,
            }
            and not contract.confirmation_required
        ):
            contract = replace(contract, confirmation_required=True)
        if contract.tool_name in self._contracts_by_tool:
            raise ValueError(f"Tool contract already registered: {contract.tool_name}")
        domain_key = (contract.system_id, contract.domain_id)
        if domain_key not in self._domains:
            raise ValueError(
                f"Cannot register contract for unknown domain: "
                f"{contract.system_id}/{contract.domain_id}"
            )
        self._contracts_by_tool[contract.tool_name] = contract
        self._contracts.append(contract)

    def get_domain(self, system_id: str, domain_id: str) -> DomainDefinition | None:
        return self._domains.get((system_id, domain_id))

    def list_domains(self, system_id: str | None = None) -> list[DomainDefinition]:
        values = list(self._domains.values())
        if system_id is None:
            return values
        return [item for item in values if item.system_id == system_id]

    def get_contract(self, tool_name: str) -> ToolContract | None:
        return self._contracts_by_tool.get(tool_name)

    def list_contracts(
        self,
        *,
        system_id: str | None = None,
        domain_id: str | None = None,
        status: Readiness | None = None,
    ) -> list[ToolContract]:
        items = list(self._contracts)
        if system_id is not None:
            items = [item for item in items if item.system_id == system_id]
        if domain_id is not None:
            items = [item for item in items if item.domain_id == domain_id]
        if status is not None:
            items = [item for item in items if item.status == status]
        return items

    def resolve_tool(
        self,
        system_id: str,
        domain_id: str,
        *,
        capability: str | None = None,
        operation: str | None = None,
        executable_only: bool = True,
    ) -> ToolContract | None:
        """Resolve one contract inside one domain. No cross-domain fallback."""
        matches = self.list_contracts(system_id=system_id, domain_id=domain_id)
        if capability is not None:
            matches = [item for item in matches if item.capability == capability]
        if operation is not None:
            matches = [item for item in matches if item.operation.value == operation]
        if executable_only:
            matches = [item for item in matches if item.is_executable]
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        for preferred in matches:
            if preferred.operation.value == "read":
                return preferred
        return matches[0]

    def list_children(self, system_id: str, parent_domain_id: str) -> list[DomainDefinition]:
        return [
            item
            for item in self.list_domains(system_id)
            if item.parent_domain_id == parent_domain_id
        ]

    def assert_executable(self, tool_name: str) -> ToolContract | None:
        contract = self.get_contract(tool_name)
        if contract is None or not contract.is_executable:
            return None
        return contract
