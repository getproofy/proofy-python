"""Scoped logging helpers for controlling httpx/httpcore verbosity.

This module installs a logging filter that:
- Always suppresses httpx/httpcore INFO-level messages (the noisy request lines)
- Allows DEBUG-level httpx/httpcore messages only inside a context manager
  and only when the environment variable PROOFYDEBUG is enabled.

Usage:
    from proofy.core.logging_scopes import httpx_debug_only_here

    with httpx_debug_only_here():
        # Only within this block, and only if PROOFYDEBUG=true, httpx/httpcore
        # DEBUG logs will be emitted. INFO remains suppressed globally.
        ...
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

# Context flag to gate DEBUG records during the scope
_HTTPX_DEBUG_SCOPE: ContextVar[bool] = ContextVar("proofy_httpx_debug_scope", default=False)


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


class _HttpxDebugGate(logging.Filter):
    """Filter that suppresses httpx/httpcore INFO logs and gates DEBUG by scope.

    - Drops INFO records from httpx/httpcore unconditionally (keeps logs quiet).
    - Allows DEBUG records from httpx/httpcore only when both conditions hold:
      * PROOFYDEBUG is enabled at process level, and
      * The current execution is inside the httpx_debug_only_here() scope.
    - Other levels (WARNING and above) pass through unaffected.
    """

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: D401
        if record.name.startswith(("httpx", "httpcore")):
            if record.levelno == logging.INFO:
                return False
            if record.levelno == logging.DEBUG:
                return _is_proofy_debug_enabled() and _HTTPX_DEBUG_SCOPE.get()
        return True


_GATE_INSTALLED = False


def _install_gate_once() -> None:
    """Install the filter on httpx/httpcore loggers once per process."""
    global _GATE_INSTALLED
    if _GATE_INSTALLED:
        return

    gate = _HttpxDebugGate()
    for logger_name in ("httpx", "httpcore"):
        logger = logging.getLogger(logger_name)
        # Avoid duplicate filters (e.g., during reloads)
        if not any(isinstance(f, _HttpxDebugGate) for f in getattr(logger, "filters", [])):
            logger.addFilter(gate)
    _GATE_INSTALLED = True


@contextmanager
def httpx_debug_only_here() -> Generator[None, None, None]:
    """Temporarily allow httpx/httpcore DEBUG logs within this scope.

    Effect is active only when the environment variable PROOFYDEBUG is truthy.
    INFO messages remain suppressed globally regardless of this setting.
    """
    _install_gate_once()

    if not _is_proofy_debug_enabled():
        # No-op scope when PROOFYDEBUG is disabled
        yield
        return

    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")

    previous_httpx_level = httpx_logger.level
    previous_httpcore_level = httpcore_logger.level

    # Elevate logger levels so DEBUG records reach handlers; the gate controls visibility
    httpx_logger.setLevel(logging.DEBUG)
    httpcore_logger.setLevel(logging.DEBUG)

    token = _HTTPX_DEBUG_SCOPE.set(True)
    try:
        yield
    finally:
        _HTTPX_DEBUG_SCOPE.reset(token)
        httpx_logger.setLevel(previous_httpx_level)
        httpcore_logger.setLevel(previous_httpcore_level)


# Install the filter at import so INFO is suppressed even without explicit scopes
_install_gate_once()


__all__ = ["httpx_debug_only_here"]
