"""Authorized tool execution. Product-specific grants are a caller hook."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from system_bridge.execution import user_id_context
from system_bridge.permissions import AuthorizationResult, PermissionService
from system_bridge.reliability import (
    ReliabilityConfig,
    RetryableToolError,
    ToolTimeoutError,
    is_retryable_tool_result,
    run_with_timeout,
    safe_internal_failure_result,
    safe_retry_exhausted_result,
    safe_timeout_result,
    sleep_backoff,
)
from system_bridge.tools import Tool, ToolRegistry, ToolResult


@dataclass(frozen=True)
class ToolExecutionResult:
    """Outcome of an authorized tool invocation attempt."""

    allowed: bool
    tool_name: str
    authorization: AuthorizationResult
    result: ToolResult | None = None
    detail: str = ""
    attempts: int = 0


SessionGrant = Callable[[str, Tool], AuthorizationResult | None]
CallerSubject = Callable[[], str | None]
RequireCallerSubject = Callable[[], bool]


class ToolGateway:
    """
    Public entry point for tool execution.

    Flow: contract readiness → system access → permission → timeout/retry →
    Tool._execute.

    An optional domain registry blocks tools that are not implemented.
    It never grants permissions. PermissionService remains the authorization
    source of truth. session_grant, when provided by the caller, may replace
    that check for one invocation.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        permission_service: PermissionService,
        reliability: ReliabilityConfig | None = None,
        domain_registry: Any = None,
        session_grant: SessionGrant | None = None,
        caller_subject: CallerSubject | None = None,
        require_caller_subject: RequireCallerSubject | None = None,
    ) -> None:
        self._tools = tool_registry
        self._permissions = permission_service
        self._reliability = reliability or ReliabilityConfig()
        self._domains = domain_registry
        self._session_grant = session_grant
        self._caller_subject = caller_subject
        self._require_caller_subject = require_caller_subject

    @property
    def reliability(self) -> ReliabilityConfig:
        return self._reliability

    def _reject_forbidden_or_non_executable(
        self, tool_name: str
    ) -> ToolExecutionResult | None:
        """DELETE and not-ready contracts never reach Tool._execute."""
        lowered = tool_name.strip().lower()
        looks_like_delete = (
            "delete" in lowered
            or lowered.endswith(".destroy")
            or ".destroy_" in lowered
        )

        if self._domains is not None:
            contract = self._domains.get_contract(tool_name)
            if contract is not None:
                action = getattr(contract.capability_action, "value", contract.capability_action)
                operation = getattr(contract.operation, "value", contract.operation)
                status = getattr(contract.status, "value", contract.status)
                if contract.is_forbidden or action == "delete":
                    auth = AuthorizationResult(
                        allowed=False,
                        reason="tool_forbidden",
                        detail=(
                            f"Tool '{tool_name}' is permanently forbidden for AI "
                            f"(action={contract.capability_action.value}, "
                            f"status={contract.status.value})."
                        ),
                    )
                    return ToolExecutionResult(
                        allowed=False,
                        tool_name=tool_name,
                        authorization=auth,
                        detail=auth.detail,
                        attempts=0,
                    )
                if operation == "destructive":
                    auth = AuthorizationResult(
                        allowed=False,
                        reason="tool_forbidden",
                        detail=f"Destructive tool '{tool_name}' is forbidden for AI.",
                    )
                    return ToolExecutionResult(
                        allowed=False,
                        tool_name=tool_name,
                        authorization=auth,
                        detail=auth.detail,
                        attempts=0,
                    )
                if status != "implemented":
                    auth = AuthorizationResult(
                        allowed=False,
                        reason="tool_not_ready",
                        detail=(
                            f"Tool '{tool_name}' is {contract.status.value} "
                            f"(domain={contract.domain_id}); not executable."
                        ),
                    )
                    return ToolExecutionResult(
                        allowed=False,
                        tool_name=tool_name,
                        authorization=auth,
                        detail=auth.detail,
                        attempts=0,
                    )
            elif looks_like_delete:
                auth = AuthorizationResult(
                    allowed=False,
                    reason="tool_forbidden",
                    detail=f"Delete-like tool '{tool_name}' is permanently forbidden for AI.",
                )
                return ToolExecutionResult(
                    allowed=False,
                    tool_name=tool_name,
                    authorization=auth,
                    detail=auth.detail,
                    attempts=0,
                )
            else:
                auth = AuthorizationResult(
                    allowed=False,
                    reason="tool_not_ready",
                    detail=f"Tool '{tool_name}' has no implemented contract.",
                )
                return ToolExecutionResult(
                    allowed=False,
                    tool_name=tool_name,
                    authorization=auth,
                    detail=auth.detail,
                    attempts=0,
                )
            return None

        auth = AuthorizationResult(
            allowed=False,
            reason="tool_not_ready",
            detail=f"Tool '{tool_name}' has no implemented contract.",
        )
        return ToolExecutionResult(
            allowed=False,
            tool_name=tool_name,
            authorization=auth,
            detail=auth.detail,
            attempts=0,
        )

    def authorize(self, user_id: str, tool_name: str) -> AuthorizationResult:
        blocked = self._reject_forbidden_or_non_executable(tool_name)
        if blocked is not None:
            return blocked.authorization

        tool = self._tools.get(tool_name)
        if tool is None:
            return AuthorizationResult(
                allowed=False,
                reason="tool_not_found",
                detail=f"Unknown tool: {tool_name}",
            )
        return self._permissions.authorize(
            user_id=user_id,
            system_id=tool.system_id,
            permission=tool.required_permission,
        )

    def _reject_caller_identity(
        self, user_id: str, tool_name: str
    ) -> ToolExecutionResult | None:
        """A verified caller may run only as that caller. HTTP mode requires one."""
        if self._caller_subject is None and self._require_caller_subject is None:
            return None
        subject = ""
        if self._caller_subject is not None:
            subject = str(self._caller_subject() or "").strip()
        requested = str(user_id or "").strip()
        if subject and subject != requested:
            auth = AuthorizationResult(
                allowed=False,
                reason="identity_mismatch",
                detail="The verified session does not match the tool caller.",
            )
            return ToolExecutionResult(
                allowed=False,
                tool_name=tool_name,
                authorization=auth,
                detail=auth.detail,
                attempts=0,
            )
        required = (
            bool(self._require_caller_subject())
            if self._require_caller_subject is not None
            else False
        )
        if required and not subject:
            auth = AuthorizationResult(
                allowed=False,
                reason="unauthenticated",
                detail="A verified session is required before a tool can run.",
            )
            return ToolExecutionResult(
                allowed=False,
                tool_name=tool_name,
                authorization=auth,
                detail=auth.detail,
                attempts=0,
            )
        return None

    def execute(
        self,
        user_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolExecutionResult:
        blocked = self._reject_caller_identity(user_id, tool_name)
        if blocked is not None:
            return blocked
        blocked = self._reject_forbidden_or_non_executable(tool_name)
        if blocked is not None:
            return blocked

        tool = self._tools.get(tool_name)
        if tool is None:
            auth = AuthorizationResult(
                allowed=False,
                reason="tool_not_found",
                detail=f"Unknown tool: {tool_name}",
            )
            return ToolExecutionResult(
                allowed=False,
                tool_name=tool_name,
                authorization=auth,
                detail=auth.detail,
                attempts=0,
            )

        auth = None
        if self._session_grant is not None:
            auth = self._session_grant(user_id, tool)
        if auth is None:
            auth = self._permissions.authorize(
                user_id=user_id,
                system_id=tool.system_id,
                permission=tool.required_permission,
            )
        if not auth.allowed:
            return ToolExecutionResult(
                allowed=False,
                tool_name=tool_name,
                authorization=auth,
                detail=auth.detail,
                attempts=0,
            )

        args = arguments or {}
        config = self._reliability
        attempt_limit = config.max_attempts if tool.retries_transient else 1
        attempts = 0
        last_result: ToolResult | None = None
        saw_timeout = False

        while attempts < attempt_limit:
            attempts += 1
            try:
                with user_id_context(user_id):
                    result = run_with_timeout(
                        lambda: tool._execute(args),
                        config.timeout_seconds,
                    )
            except ToolTimeoutError:
                saw_timeout = True
                last_result = safe_timeout_result()
                if attempts >= attempt_limit:
                    break
                sleep_backoff(attempts - 1, config.backoff_seconds)
                continue
            except RetryableToolError:
                last_result = ToolResult(
                    success=False,
                    error="The tool failed temporarily. Please try again later.",
                    error_code="TRANSIENT_ERROR",
                    data={},
                )
                if attempts >= attempt_limit:
                    break
                sleep_backoff(attempts - 1, config.backoff_seconds)
                continue
            except Exception:
                return ToolExecutionResult(
                    allowed=True,
                    tool_name=tool_name,
                    authorization=auth,
                    result=safe_internal_failure_result(),
                    detail="executed",
                    attempts=attempts,
                )

            if result.success:
                return ToolExecutionResult(
                    allowed=True,
                    tool_name=tool_name,
                    authorization=auth,
                    result=result,
                    detail="executed",
                    attempts=attempts,
                )

            last_result = result
            if not is_retryable_tool_result(result):
                return ToolExecutionResult(
                    allowed=True,
                    tool_name=tool_name,
                    authorization=auth,
                    result=result,
                    detail="executed",
                    attempts=attempts,
                )

            if attempts >= attempt_limit:
                break
            sleep_backoff(attempts - 1, config.backoff_seconds)

        if saw_timeout and (
            last_result is None or last_result.error_code == "TIMEOUT"
        ):
            final = last_result or safe_timeout_result()
        elif last_result is not None and is_retryable_tool_result(last_result):
            final = safe_retry_exhausted_result()
        else:
            final = last_result or safe_retry_exhausted_result()

        return ToolExecutionResult(
            allowed=True,
            tool_name=tool_name,
            authorization=auth,
            result=final,
            detail="executed",
            attempts=attempts,
        )
