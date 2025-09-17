"""Runtime context management for test execution."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from ..export.attachments import (
    cache_attachment,
    should_cache_for_mode,
)
from ..hooks.manager import get_plugin_manager


@dataclass
class TestContext:
    """Runtime context for a single test execution.

    Holds per-test data that can be modified during test execution
    via decorators, runtime API calls, or hook implementations.
    """

    __test__: ClassVar[bool] = False  # Prevent pytest from treating this as a test

    # Test identification
    test_id: str | None = None

    # Display properties
    name: str | None = None
    description: str | None = None
    severity: str | None = None

    # Metadata and attributes
    metadata: dict[str, Any] = field(default_factory=dict)
    attributes: dict[str, Any] = field(default_factory=dict)  # Old project compatibility
    tags: list[str] = field(default_factory=list)

    # Attachments
    files: list[dict[str, Any]] = field(default_factory=list)

    # Server integration
    server_id: int | None = None  # Server-assigned test result ID
    run_id: int | None = None  # Server-assigned run ID


@dataclass
class SessionContext:
    """Runtime context for an entire test session."""

    session_id: str
    run_name: str | None = None
    run_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    test_contexts: dict[str, TestContext] = field(default_factory=dict)


# Thread-local storage for contexts
_LOCAL = threading.local()


def _get_local_test_context() -> TestContext:
    """Get or create the test context for the current thread."""
    ctx = getattr(_LOCAL, "test_ctx", None)
    if ctx is None:
        ctx = TestContext()
        _LOCAL.test_ctx = ctx
    return ctx


def _get_local_session_context() -> SessionContext | None:
    """Get the session context for the current thread."""
    return getattr(_LOCAL, "session_ctx", None)


# ========== Test Context Management ==========


def set_current_test_context(ctx: TestContext | None) -> None:
    """Set or clear the current test context for the active thread.

    Args:
        ctx: Test context to set, or None to clear
    """
    if ctx is None:
        if hasattr(_LOCAL, "test_ctx"):
            delattr(_LOCAL, "test_ctx")
        return
    _LOCAL.test_ctx = ctx


def get_current_test_context() -> TestContext:
    """Get the current test context (auto-creates if missing).

    Returns:
        TestContext: Current test context
    """
    return _get_local_test_context()


def get_test_context(test_id: str) -> TestContext | None:
    """Get test context by ID from session context.

    Args:
        test_id: Test identifier

    Returns:
        TestContext if found, None otherwise
    """
    session_ctx = _get_local_session_context()
    if session_ctx:
        return session_ctx.test_contexts.get(test_id)
    return None


# ========== Session Context Management ==========


def set_current_session_context(ctx: SessionContext | None) -> None:
    """Set or clear the current session context.

    Args:
        ctx: Session context to set, or None to clear
    """
    if ctx is None:
        if hasattr(_LOCAL, "session_ctx"):
            delattr(_LOCAL, "session_ctx")
        return
    _LOCAL.session_ctx = ctx


def get_current_session_context() -> SessionContext | None:
    """Get the current session context.

    Returns:
        SessionContext if set, None otherwise
    """
    return _get_local_session_context()


# ========== Context Stack (for nested contexts) ==========


def push_test_context(ctx: TestContext) -> None:
    """Push a new test context onto the stack.

    Args:
        ctx: Test context to push
    """
    stack: list[TestContext] = getattr(_LOCAL, "ctx_stack", [])
    stack.append(get_current_test_context())
    _LOCAL.ctx_stack = stack
    set_current_test_context(ctx)


def pop_test_context() -> TestContext | None:
    """Pop the previous test context from the stack.

    Returns:
        Previous test context, or None if stack is empty
    """
    stack: list[TestContext] = getattr(_LOCAL, "ctx_stack", [])
    if not stack:
        return None

    previous_ctx = stack.pop()
    _LOCAL.ctx_stack = stack
    set_current_test_context(previous_ctx)
    return previous_ctx


# ========== Metadata Management ==========


def add_metadata(key: str, value: Any, test_id: str | None = None) -> None:
    """Add metadata to test context.

    Args:
        key: Metadata key
        value: Metadata value
        test_id: Target test ID (current test if None)
    """
    if test_id:
        ctx = get_test_context(test_id)
        if not ctx:
            return
    else:
        ctx = _get_local_test_context()

    ctx.metadata[key] = value

    # Trigger hook
    pm = get_plugin_manager()
    pm.hook.proofy_add_attributes(test_id=test_id or ctx.test_id, attributes={key: value})


def add_attributes(test_id: str | None = None, **kwargs: Any) -> None:
    """Add multiple attributes to test context.

    Args:
        test_id: Target test ID (current test if None)
        **kwargs: Attributes to add
    """
    if test_id:
        ctx = get_test_context(test_id)
        if not ctx:
            return
    else:
        ctx = _get_local_test_context()

    ctx.attributes.update(kwargs)
    ctx.metadata.update(kwargs)  # Also add to metadata for compatibility

    # Trigger hook
    pm = get_plugin_manager()
    pm.hook.proofy_add_attributes(test_id=test_id or ctx.test_id, attributes=kwargs)


def add_tag(tag: str, test_id: str | None = None) -> None:
    """Add a tag to test context.

    Args:
        tag: Tag to add
        test_id: Target test ID (current test if None)
    """
    if test_id:
        ctx = get_test_context(test_id)
        if not ctx:
            return
    else:
        ctx = _get_local_test_context()

    if tag not in ctx.tags:
        ctx.tags.append(tag)

        # Trigger hook
        pm = get_plugin_manager()
        pm.hook.proofy_add_tags(test_id=test_id or ctx.test_id, tags=[tag])


def add_tags(tags: list[str], test_id: str | None = None) -> None:
    """Add multiple tags to test context.

    Args:
        tags: Tags to add
        test_id: Target test ID (current test if None)
    """
    if test_id:
        ctx = get_test_context(test_id)
        if not ctx:
            return
    else:
        ctx = _get_local_test_context()

    new_tags = []
    for tag in tags:
        if tag not in ctx.tags:
            ctx.tags.append(tag)
            new_tags.append(tag)

    if new_tags:
        # Trigger hook
        pm = get_plugin_manager()
        pm.hook.proofy_add_tags(test_id=test_id or ctx.test_id, tags=new_tags)


# ========== Attachment Management ==========


def add_file(
    file: str | Path,
    *,
    name: str,
    content_type: str | None = None,
    mime_type: str | None = None,  # Alias for content_type
    extension: str | None = None,
    test_id: str | None = None,
) -> None:
    """Add a file attachment to test context.

    Args:
        file: Path to the file
        name: Display name for the attachment
        content_type: MIME type of the file
        mime_type: Alias for content_type (for compatibility)
        extension: File extension
        test_id: Target test ID (current test if None)
    """
    if test_id:
        ctx = get_test_context(test_id)
        if not ctx:
            return
    else:
        ctx = _get_local_test_context()

    # Use mime_type if content_type not provided
    final_content_type = content_type or mime_type

    original_path = Path(file)
    path_to_store = original_path

    # Decide caching strategy using env-based mode (works across frameworks)
    try:
        mode = os.getenv("PROOFY_MODE")
        if should_cache_for_mode(mode):
            # Copy to cache for reliability (will raise if source missing)
            path_to_store = cache_attachment(original_path)
    except Exception:
        # If caching fails, fall back to original path
        path_to_store = original_path

    file_info = {
        "name": name,
        "path": path_to_store.as_posix(),
        "original_path": str(original_path),
        "content_type": final_content_type,
        "mime_type": final_content_type,  # Compatibility
        "extension": extension,
    }

    ctx.files.append(file_info)

    # Trigger hook
    pm = get_plugin_manager()
    pm.hook.proofy_add_attachment(
        test_id=test_id or ctx.test_id,
        file_path=path_to_store.as_posix(),
        name=name,
        mime_type=final_content_type,
    )


def add_attachment(
    file: str | Path,
    *,
    name: str,
    mime_type: str | None = None,
    extension: str | None = None,
    test_id: str | None = None,
) -> None:
    """Add an attachment to test context (convenience wrapper for add_file).

    Args:
        file: Path to the file
        name: Display name for the attachment
        mime_type: MIME type of the file
        extension: File extension
        test_id: Target test ID (current test if None)
    """
    add_file(file=file, name=name, mime_type=mime_type, extension=extension, test_id=test_id)
