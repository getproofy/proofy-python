"""Stable public API facade delegating to runtime implementations."""

from __future__ import annotations

from pathlib import Path
from typing import IO, Any

from .._impl.context import get_context_service
from .._impl.context.models import SessionContext
from .client import ArtifactType

_context_service = get_context_service()


def add_attributes(**kwargs: Any) -> None:
    _context_service.add_attributes(**kwargs)


def add_tag(tag: str) -> None:
    _context_service.add_tag(tag)


def add_tags(tags: list[str]) -> None:
    _context_service.add_tags(tags)


def set_name(name: str) -> None:
    _context_service.set_name(name)


def set_title(title: str) -> None:
    # Convenience alias matching decorator naming
    _context_service.set_name(title)


def add_attachment(
    file: str | Path | bytes | bytearray | IO[bytes],
    *,
    name: str,
    mime_type: str | None = None,
    extension: str | None = None,
    artifact_type: ArtifactType | int = ArtifactType.ATTACHMENT,
) -> None:
    _context_service.attach(
        file,
        name=name,
        mime_type=mime_type,
        extension=extension,
        artifact_type=int(artifact_type),
    )


def set_description(description: str) -> None:
    _context_service.set_description(description)


def set_severity(severity: str) -> None:
    _context_service.set_severity(severity)


def get_current_test_id() -> str | None:
    ctx = _context_service.current_test()
    return ctx.id if ctx else None


# --- Run management ---
def _get_session() -> SessionContext | None:
    return _context_service.session_ctx


def set_run_name(name: str) -> None:
    sess = _get_session()
    if sess is None:
        raise RuntimeError("Session in not initialized yet")
    sess.run_name = name


def get_current_run_id() -> int | None:
    sess = _get_session()
    return sess.run_id if sess else None


__all__ = [
    "add_attachment",
    "add_attributes",
    "add_tag",
    "add_tags",
    "get_current_run_id",
    "get_current_test_id",
    "set_description",
    "set_name",
    "set_title",
    "set_run_name",
    "set_severity",
]
