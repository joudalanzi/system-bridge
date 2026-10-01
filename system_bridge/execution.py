"""Per-request execution context for tools."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_current_user_id: ContextVar[str | None] = ContextVar(
    "tool_current_user_id",
    default=None,
)


def get_current_user_id() -> str | None:
    return _current_user_id.get()


@contextmanager
def user_id_context(user_id: str) -> Iterator[None]:
    """Bind the caller id for the duration of a tool execution."""
    token = _current_user_id.set(user_id)
    try:
        yield
    finally:
        _current_user_id.reset(token)
