"""Scoped logging helpers for controlling httpx/httpcore verbosity.

This module provides a context manager that can temporarily adjust visibility
of ``httpx``/``httpcore`` logs without affecting global user logging config.

- Outside the context, nothing is installed or modified; logging behaves as-is.
- Inside the context:
  * When PROOFYDEBUG is truthy ("true", "1", "yes", "on"), INFO/DEBUG logs
    from httpx/httpcore are allowed by temporarily setting their logger levels
    to DEBUG for the duration of the scope.
  * When PROOFYDEBUG is not enabled, INFO/DEBUG logs from httpx/httpcore are
    suppressed within the scope.

Usage:
    from proofy._internal.logging_scopes import httpx_debug_logging_scope

    with httpx_debug_logging_scope():
        # Inside this block, and only if PROOFYDEBUG=true, httpx/httpcore
        # DEBUG and INFO logs will be emitted.
        ...
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

# Context flag to gate DEBUG records during the scope
_HTTPX_DEBUG_SCOPE_ACTIVE: ContextVar[bool] = ContextVar(
    "proofy_httpx_debug_scope_active", default=False
)


def _is_truthy(value: str | None) -> bool:
    """Parse common truthy strings to bool.

    Accepts: "true", "1", "yes", "on" (case-insensitive).
    """
    if value is None:
        return False
    return value.strip().lower() in {"true", "1", "yes", "on"}


def _is_proofy_debug_enabled() -> bool:
    """Return True if PROOFYDEBUG env var enables debug logging scopes."""
    return _is_truthy(os.getenv("PROOFYDEBUG"))


class _HttpxVisibilityFilter(logging.Filter):
    """Filter that suppresses httpx/httpcore INFO logs and gates DEBUG by scope.

    - Drops INFO records from httpx/httpcore by default (keeps logs quiet).
    - Allows DEBUG and INFO records from httpx/httpcore only when both conditions hold:
      * PROOFYDEBUG is enabled at process level, and
      * The current execution is inside the httpx_debug_logging_scope() scope.
    - Other levels (WARNING and above) pass through unaffected.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if record.name.startswith(("httpx", "httpcore")) and record.levelno in (
            logging.INFO,
            logging.DEBUG,
        ):
            return _is_proofy_debug_enabled() and _HTTPX_DEBUG_SCOPE_ACTIVE.get()
        return True


@contextmanager
def httpx_debug_logging_scope() -> Generator[None, None, None]:
    """Temporarily allow httpx/httpcore DEBUG logs within this scope.

    Outside the scope nothing is modified. Within the scope:
    - If PROOFYDEBUG is truthy, INFO/DEBUG from httpx/httpcore are made visible
      by elevating their logger levels to DEBUG.
    - If PROOFYDEBUG is falsy, INFO/DEBUG from httpx/httpcore are suppressed.
    """
    visibility_filter = _HttpxVisibilityFilter()
    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")

    previous_httpx_level = httpx_logger.level
    previous_httpcore_level = httpcore_logger.level

    # Activate scope flag and install filter only for the duration of the context
    token = _HTTPX_DEBUG_SCOPE_ACTIVE.set(True)
    httpx_logger.addFilter(visibility_filter)
    httpcore_logger.addFilter(visibility_filter)

    debug_enabled = _is_proofy_debug_enabled()
    if debug_enabled:
        # Elevate logger levels so DEBUG records reach handlers during scope
        httpx_logger.setLevel(logging.DEBUG)
        httpcore_logger.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        from contextlib import suppress

        _HTTPX_DEBUG_SCOPE_ACTIVE.reset(token)
        # Remove our temporary filter
        with suppress(Exception):
            httpx_logger.removeFilter(visibility_filter)
        with suppress(Exception):
            httpcore_logger.removeFilter(visibility_filter)
        httpx_logger.setLevel(previous_httpx_level)
        httpcore_logger.setLevel(previous_httpcore_level)


__all__ = ["httpx_debug_logging_scope"]
