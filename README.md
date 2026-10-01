# system-bridge

`system-bridge` is a small Python library that lets a host application register external systems behind one tool gateway.

The installable name is `system-bridge`. The import package is `system_bridge`.

## What it does

A host supplies one or more `SystemPack` implementations. `build_runtime()` registers each pack's system and tools, then returns a `BridgeRuntime` with:

- a system registry
- a tool registry
- a permission service
- a tool gateway
- the domain-contract catalog the host passed in

Tool calls go through `ToolGateway.execute`. The gateway checks the caller's permission, and it refuses a tool that has no implemented contract.

## What it does not contain

The package has no product adapter, no product permission names, and no application orchestrator. A product such as Crow stays in the host application and is added with a pack. The library does not import that pack, and an empty `build_runtime()` starts with zero business-system tools.

## Install

```bash
python -m pip install /path/to/this/project
```

From another project, with that project's own virtual environment:

```bash
python -m pip install "C:\path\to\this\project"
```

No extra `PYTHONPATH` entry is required. The other project does not need this repository's application modules.

## Create a pack

```python
from system_bridge import (
    DomainDefinition,
    DomainRegistry,
    OperationKind,
    Readiness,
    SystemAdapter,
    SystemDefinition,
    SystemPack,
    Tool,
    ToolContract,
    ToolDefinition,
    ToolResult,
    build_runtime,
)


class NotesAdapter(SystemAdapter):
    def __init__(self) -> None:
        self._definition = SystemDefinition(
            system_id="notes",
            name="Notes",
            enabled=True,
        )

    @property
    def definition(self) -> SystemDefinition:
        return self._definition


class NotesTool(Tool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="notes.list",
            system_id="notes",
            required_permission="notes.read",
            description="List notes.",
        )

    def _execute(self, arguments: dict) -> ToolResult:
        return ToolResult(success=True, data={"items": []})


class NotesPack(SystemPack):
    def adapter(self) -> SystemAdapter:
        return NotesAdapter()

    def contribute_tools(self, registry) -> None:
        registry.register(NotesTool())
```

A pack may also return a `ReliabilityConfig` from `reliability()`. It can only register tools whose `system_id` matches its own adapter. The library rejects any other registration.

A working copy of this pack lives in `examples/notes_pack.py`. That file is not part of the installed package.

## Register tools

Tools are registered inside `contribute_tools`. The runtime passes a registry scoped to that pack. The generic `ToolRegistry` starts empty. Nothing in the library registers a product tool on its own.

## Permissions

The host passes a grant map or its own `PermissionService`. The library's `MemoryPermissionService` only stores what the host gives it. The gateway is the enforcement point: a pack cannot skip that check by calling a tool method itself. `execute` is the supported path.

```python
runtime = build_runtime(
    extra_packs=[NotesPack()],
    grants={"user-1": {"notes": {"notes.read"}}},
    domain_registry=contracts,
)
runtime.gateway.execute("user-1", "notes.list")  # allowed when the contract exists
runtime.gateway.execute("user-2", "notes.list")  # denied
```

## Contracts

Pass a `DomainRegistry` when a tool should be executable. Register the domain, then the tool contract, with `status` implemented. If the runtime has no contract catalog, or the tool has no contract, the gateway denies the call.

## A second system

Add another pack to `extra_packs`. Do not edit `system_bridge`.

```python
empty = build_runtime()

runtime = build_runtime(
    extra_packs=[NotesPack()],
    grants={"user-1": {"notes": {"notes.read"}}},
    domain_registry=contracts,
)
```

`build_runtime()` with no packs is valid. It exposes the gateway and registers no business system.

## How a host loads several systems

The host builds one runtime and lists every pack:

```python
runtime = build_runtime(
    extra_packs=[FirstPack(), SecondPack()],
    permission_factory=host_permission_service,
    domain_registry=host_contracts,
    gateway_cls=HostGateway,
)
```

`permission_factory` receives the system registry after the packs are registered. `gateway_cls` lets the host wrap execution policy without putting that policy in the library. Product packs stay in the host.
