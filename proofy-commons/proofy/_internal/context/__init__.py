"""Internal context API.

This exposes ContextService and helpers under `_internal`.
"""

from __future__ import annotations

from .backend import ThreadLocalBackend
from .models import SessionContext
from .service import ContextService

_global_backend = ThreadLocalBackend()
_global_service: ContextService | None = None


def get_context_service() -> ContextService:
    """Return shared ContextService instance (thread-local storage)."""
    global _global_service
    if _global_service is None:
        _global_service = ContextService(backend=_global_backend)
    return _global_service


__all__ = [
    "ContextService",
    "ThreadLocalBackend",
    "get_context_service",
    "SessionContext",
]
