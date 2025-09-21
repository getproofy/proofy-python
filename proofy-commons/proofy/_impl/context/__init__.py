"""Private implementation for Proofy context management.

This package contains internal, unstable APIs for managing test and session
context. External users should not import from here directly. Public wrappers
may be provided under stable modules.
"""

from __future__ import annotations

from .backend import ThreadLocalBackend
from .service import ContextService  # re-export for internal convenience

_global_backend = ThreadLocalBackend()
_global_service = ContextService(backend=_global_backend)


def get_context_service() -> ContextService:
    """Return shared ContextService instance (thread-local storage)."""
    return _global_service


__all__ = ["get_context_service", "ContextService", "ThreadLocalBackend"]
