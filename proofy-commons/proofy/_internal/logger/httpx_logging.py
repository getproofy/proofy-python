"""Scoped logging helpers for controlling httpx/httpcore verbosity.

This module installs a logging filter that:
- Always suppresses httpx/httpcore INFO-level messages (the noisy request lines)
- Allows DEBUG-level httpx/httpcore messages only inside a context manager
  and only when Proofy debug logging is enabled (PFDEBUG, PF_LOG_LEVEL=DEBUG,
  or the legacy PROOFYDEBUG flag) and the scope is active.

Usage:
    from proofy._internal.logger.httpx_logging import httpx_debug_only_here

    with httpx_debug_only_here():
        # Only within this block, and only if Proofy debug logging is enabled,
        # httpx/httpcore DEBUG logs will be emitted. INFO remains suppressed globally.
        ...
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from .logging import is_debug_logging_enabled

# Context flag to gate DEBUG records during the scope
_HTTPX_DEBUG_SCOPE: ContextVar[bool] = ContextVar("proofy_httpx_debug_scope", default=False)


def _is_proofy_debug_enabled() -> bool:
    """Return True if Proofy debug logging is enabled via global settings."""
    return is_debug_logging_enabled()


class _HttpxDebugGate(logging.Filter):
    """Filter that suppresses httpx/httpcore INFO logs and gates DEBUG by scope.

    - Drops INFO records from httpx/httpcore unconditionally (keeps logs quiet).
    - Allows DEBUG records from httpx/httpcore only when both conditions hold:
      * Proofy debug logging is enabled at process level, and
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

    Effect is active only when Proofy debug logging is enabled at process level.
    INFO messages remain suppressed globally regardless of this setting.
    """
    _install_gate_once()

    if not _is_proofy_debug_enabled():
        # No-op scope when Proofy debug logging is disabled
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
