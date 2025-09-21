"""Stable public API facade delegating to runtime implementations.

This module provides a forward-compatible import path for user code:

    from proofy import add_attachment, add_metadata

Internally it currently delegates to proofy.runtime.api. In the future this
may switch to using ContextService directly without breaking imports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._impl.context import get_context_service
from ._impl.context.models import SessionContext
from ._impl.context.models import TestResult as TestContext
from .hooks.manager import get_plugin_manager


# New delegations to ContextService
def _ensure_current_test_context() -> None:
    svc = get_context_service()
    if svc.backend.get_test() is None:
        svc.backend.set_test(TestContext())


def get_current_test_context() -> TestContext:
    svc = get_context_service()
    ctx = svc.current_test()
    if ctx is None:
        _ensure_current_test_context()
        ctx = svc.current_test()
    return ctx  # type: ignore[return-value]


def set_current_test_context(ctx: TestContext | None) -> None:
    svc = get_context_service()
    svc.backend.set_test(ctx)


def get_current_session_context() -> SessionContext | None:
    svc = get_context_service()
    return svc.backend.get_session()


def set_current_session_context(ctx: SessionContext | None) -> None:
    svc = get_context_service()
    svc.backend.set_session(ctx)


def add_metadata(key: str, value: Any, test_id: str | None = None) -> None:
    svc = get_context_service()
    _ensure_current_test_context()
    if test_id is not None:
        # Switch current test temporarily is out of scope; rely on plugin lifecycle
        svc.set_metadata(key, value)
    else:
        svc.set_metadata(key, value)


def add_attributes(test_id: str | None = None, **kwargs: Any) -> None:
    svc = get_context_service()
    _ensure_current_test_context()
    svc.add_attributes(**kwargs)


def add_tag(tag: str, test_id: str | None = None) -> None:
    svc = get_context_service()
    _ensure_current_test_context()
    svc.add_tag(tag)


def add_tags(tags: list[str], test_id: str | None = None) -> None:
    svc = get_context_service()
    _ensure_current_test_context()
    svc.add_tags(tags)


def add_attachment(
    file: str | Path,
    *,
    name: str,
    mime_type: str | None = None,
    extension: str | None = None,
    test_id: str | None = None,
) -> None:
    add_file(
        file=file,
        name=name,
        mime_type=mime_type,
        extension=extension,
        test_id=test_id,
    )


def add_file(
    file: str | Path,
    *,
    name: str,
    content_type: str | None = None,
    mime_type: str | None = None,
    extension: str | None = None,
    test_id: str | None = None,
) -> None:
    svc = get_context_service()
    _ensure_current_test_context()
    effective_mime = content_type or mime_type
    svc.attach(file, name=name, mime_type=effective_mime, extension=extension)


# Name/description/severity now via ContextService
def set_name(name: str, test_id: str | None = None) -> None:
    svc = get_context_service()
    _ensure_current_test_context()
    svc.set_name(name)


def set_description(description: str, test_id: str | None = None) -> None:
    svc = get_context_service()
    _ensure_current_test_context()
    svc.set_description(description)


def set_severity(severity: str, test_id: str | None = None) -> None:
    svc = get_context_service()
    _ensure_current_test_context()
    svc.set_severity(severity)


# Back-compat small helpers implemented via hooks/ContextService
def set_run_name(name: str) -> None:
    pm = get_plugin_manager()
    pm.hook.proofy_set_run_name(name=name)


def add_run_name(name: str) -> None:  # Legacy alias
    set_run_name(name)


def get_current_test_id() -> str | None:
    svc = get_context_service()
    ctx = svc.current_test()
    return ctx.test_id if ctx else None


def get_current_server_id() -> int | None:
    svc = get_context_service()
    ctx = svc.current_test()
    return ctx.server_id if ctx else None


def get_current_run_id() -> int | None:
    svc = get_context_service()
    sess = svc.backend.get_session()
    return sess.run_id if sess else None


# Convenience tag helpers
def mark_as_critical(test_id: str | None = None) -> None:
    set_severity("critical")


def mark_as_high(test_id: str | None = None) -> None:
    set_severity("high")


def mark_as_medium(test_id: str | None = None) -> None:
    set_severity("medium")


def mark_as_low(test_id: str | None = None) -> None:
    set_severity("low")


def tag_as_smoke(test_id: str | None = None) -> None:
    add_tag("smoke")


def tag_as_regression(test_id: str | None = None) -> None:
    add_tag("regression")


def tag_as_integration(test_id: str | None = None) -> None:
    add_tag("integration")


def tag_as_unit(test_id: str | None = None) -> None:
    add_tag("unit")


def upload_file(
    file: str,
    name: str,
    content_type: str,
    extension: str,
    test_id: str | None = None,
) -> None:
    add_file(file=file, name=name, content_type=content_type, extension=extension)


__all__ = [
    "add_attachment",
    "add_attributes",
    "add_file",
    "add_metadata",
    "add_run_name",
    "add_tag",
    "add_tags",
    "get_current_run_id",
    "get_current_server_id",
    "get_current_test_id",
    "mark_as_critical",
    "mark_as_high",
    "mark_as_low",
    "mark_as_medium",
    "set_description",
    "set_name",
    "set_run_name",
    "set_severity",
    "tag_as_integration",
    "tag_as_regression",
    "tag_as_smoke",
    "tag_as_unit",
    "upload_file",
]
