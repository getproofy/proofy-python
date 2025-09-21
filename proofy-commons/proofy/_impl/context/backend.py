"""Context backend abstractions and thread-local implementation."""

from __future__ import annotations

import threading
from typing import Protocol

from proofy.core.models import TestResult

from .models import SessionContext


class ContextBackend(Protocol):
    """Abstract storage for contexts."""

    def set_session(self, ctx: SessionContext | None) -> None: ...
    def get_session(self) -> SessionContext | None: ...

    def set_test(self, ctx: TestResult | None) -> None: ...
    def get_test(self) -> TestResult | None: ...


class ThreadLocalBackend:
    """Backend storing contexts in thread-local storage."""

    def __init__(self) -> None:
        self._local = threading.local()

    def set_session(self, ctx: SessionContext | None) -> None:
        if ctx is None:
            if hasattr(self._local, "proofy_session_ctx"):
                delattr(self._local, "proofy_session_ctx")
            return
        self._local.proofy_session_ctx = ctx

    def get_session(self) -> SessionContext | None:
        return getattr(self._local, "proofy_session_ctx", None)

    def set_test(self, ctx: TestResult | None) -> None:
        if ctx is None:
            if hasattr(self._local, "proofy_test_ctx"):
                delattr(self._local, "proofy_test_ctx")
            return
        self._local.proofy_test_ctx = ctx

    def get_test(self) -> TestResult | None:
        return getattr(self._local, "proofy_test_ctx", None)
