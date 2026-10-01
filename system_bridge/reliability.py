"""Configurable timeout and retry helpers for tool execution."""

from __future__ import annotations

import contextvars
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Callable, TypeVar

from system_bridge.tools import ToolResult

T = TypeVar("T")

ERROR_TIMEOUT = "TIMEOUT"
ERROR_RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
ERROR_VALIDATION = "VALIDATION_ERROR"
ERROR_TRANSIENT = "TRANSIENT_ERROR"
ERROR_AUTHORIZATION = "AUTHORIZATION_DENIED"
ERROR_AUTHENTICATION = "AUTHENTICATION_ERROR"
ERROR_INTERNAL = "INTERNAL_ERROR"
ERROR_PERMISSION = "PERMISSION_DENIED"
ERROR_NOT_FOUND = "NOT_FOUND"
ERROR_RATE_LIMITED = "RATE_LIMITED"

_NON_RETRYABLE_CODES = frozenset(
    {
        ERROR_VALIDATION,
        ERROR_AUTHORIZATION,
        ERROR_AUTHENTICATION,
        ERROR_PERMISSION,
        ERROR_NOT_FOUND,
    }
)


@dataclass(frozen=True)
class ReliabilityConfig:
    """Gateway-level reliability policy."""

    timeout_seconds: float = 5.0
    max_attempts: int = 3
    backoff_seconds: float = 0.05

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.backoff_seconds < 0:
            raise ValueError("backoff_seconds must be >= 0")


class RetryableToolError(Exception):
    """Transient tool failure that may be retried."""

    def __init__(self, message: str = "Transient tool failure") -> None:
        super().__init__(message)


class ToolTimeoutError(Exception):
    """Raised when a single tool attempt exceeds the configured timeout."""

    def __init__(self, message: str = "Tool execution timed out") -> None:
        super().__init__(message)


def run_with_timeout(func: Callable[[], T], timeout_seconds: float) -> T:
    """Run a sync callable with a hard timeout (preserves ContextVars)."""
    ctx = contextvars.copy_context()

    def _runner() -> T:
        return ctx.run(func)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_runner)
        try:
            return future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            raise ToolTimeoutError("Tool execution timed out") from exc


def is_retryable_tool_result(result: ToolResult) -> bool:
    """Validation and auth failures are never retried."""
    if result.success:
        return False
    code = result.error_code
    if code in _NON_RETRYABLE_CODES:
        return False
    if code in {ERROR_TRANSIENT, ERROR_RATE_LIMITED}:
        return True
    return False


def safe_timeout_result() -> ToolResult:
    return ToolResult(
        success=False,
        error="The tool timed out. Please try again later.",
        error_code=ERROR_TIMEOUT,
        data={},
    )


def safe_retry_exhausted_result() -> ToolResult:
    return ToolResult(
        success=False,
        error="The tool failed after multiple attempts. Please try again later.",
        error_code=ERROR_RETRY_EXHAUSTED,
        data={},
    )


def safe_internal_failure_result() -> ToolResult:
    return ToolResult(
        success=False,
        error="The tool failed unexpectedly. Please try again later.",
        error_code=ERROR_INTERNAL,
        data={},
    )


def sleep_backoff(attempt_index: int, backoff_seconds: float) -> None:
    """Linear backoff: backoff * attempt_number (1-based)."""
    if backoff_seconds <= 0:
        return
    time.sleep(backoff_seconds * (attempt_index + 1))
