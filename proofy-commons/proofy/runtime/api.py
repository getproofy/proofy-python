"""Runtime API for interacting with Proofy during test execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..hooks.manager import get_plugin_manager
from .context import (
    add_attachment as _add_attachment,
    add_attributes as _add_attributes,
    add_file as _add_file,
    add_metadata as _add_metadata,
    add_tag as _add_tag,
    add_tags as _add_tags,
    get_current_test_context,
)

# ========== Test Metadata API ==========

def set_name(name: str, test_id: Optional[str] = None) -> None:
    """Set the display name for a test.
    
    Args:
        name: New display name
        test_id: Target test ID (current test if None)
    """
    ctx = get_current_test_context()
    if test_id is None:
        test_id = ctx.test_id
    
    ctx.name = name
    
    # Trigger hook
    pm = get_plugin_manager()
    pm.hook.proofy_set_name(test_id=test_id, name=name)


def set_description(description: str, test_id: Optional[str] = None) -> None:
    """Set the description for a test.
    
    Args:
        description: Test description
        test_id: Target test ID (current test if None)
    """
    ctx = get_current_test_context()
    if test_id is None:
        test_id = ctx.test_id
    
    ctx.description = description
    
    # Trigger hook
    pm = get_plugin_manager()
    pm.hook.proofy_set_description(test_id=test_id, description=description)


def set_severity(severity: str, test_id: Optional[str] = None) -> None:
    """Set the severity level for a test.
    
    Args:
        severity: Severity level (e.g., 'critical', 'high', 'medium', 'low')
        test_id: Target test ID (current test if None)
    """
    ctx = get_current_test_context()
    if test_id is None:
        test_id = ctx.test_id
    
    ctx.severity = severity
    
    # Trigger hook
    pm = get_plugin_manager()
    pm.hook.proofy_set_severity(test_id=test_id, severity=severity)


def add_metadata(key: str, value: Any, test_id: Optional[str] = None) -> None:
    """Add a metadata key-value pair to a test.
    
    Args:
        key: Metadata key
        value: Metadata value
        test_id: Target test ID (current test if None)
    """
    _add_metadata(key, value, test_id)


def add_attributes(test_id: Optional[str] = None, **kwargs: Any) -> None:
    """Add multiple attributes to a test.
    
    Args:
        test_id: Target test ID (current test if None)
        **kwargs: Attributes to add
    """
    _add_attributes(test_id, **kwargs)


def add_tag(tag: str, test_id: Optional[str] = None) -> None:
    """Add a tag to a test.
    
    Args:
        tag: Tag to add
        test_id: Target test ID (current test if None)
    """
    _add_tag(tag, test_id)


def add_tags(tags: List[str], test_id: Optional[str] = None) -> None:
    """Add multiple tags to a test.
    
    Args:
        tags: Tags to add
        test_id: Target test ID (current test if None)
    """
    _add_tags(tags, test_id)


# ========== Attachment API ==========

def add_attachment(
    file: Union[str, Path],
    *,
    name: str,
    mime_type: Optional[str] = None,
    extension: Optional[str] = None,
    test_id: Optional[str] = None,
) -> None:
    """Add an attachment to a test.
    
    Args:
        file: Path to the file to attach
        name: Display name for the attachment
        mime_type: MIME type of the file
        extension: File extension
        test_id: Target test ID (current test if None)
    """
    _add_attachment(
        file=file,
        name=name,
        mime_type=mime_type,
        extension=extension,
        test_id=test_id
    )


def add_file(
    file: Union[str, Path],
    *,
    name: str,
    content_type: Optional[str] = None,
    mime_type: Optional[str] = None,
    extension: Optional[str] = None,
    test_id: Optional[str] = None,
) -> None:
    """Add a file attachment to a test.
    
    Args:
        file: Path to the file to attach
        name: Display name for the attachment
        content_type: MIME type of the file
        mime_type: Alias for content_type
        extension: File extension
        test_id: Target test ID (current test if None)
    """
    _add_file(
        file=file,
        name=name,
        content_type=content_type,
        mime_type=mime_type,
        extension=extension,
        test_id=test_id
    )


# ========== Run Management API ==========

def set_run_name(name: str) -> None:
    """Set the name for the current test run.
    
    Args:
        name: New run name
    """
    pm = get_plugin_manager()
    pm.hook.proofy_set_run_name(name=name)


# ========== Legacy Compatibility API (from old project) ==========

def upload_file(
    file: str,
    name: str,
    content_type: str,
    extension: str,
    test_id: Optional[str] = None,
) -> None:
    """Legacy API for uploading files (compatibility with old project).
    
    Args:
        file: File path
        name: File name
        content_type: MIME type
        extension: File extension
        test_id: Target test ID (current test if None)
    """
    add_file(
        file=file,
        name=name,
        content_type=content_type,
        extension=extension,
        test_id=test_id
    )


def add_run_name(name: str) -> None:
    """Legacy API for setting run name (compatibility with old project).
    
    Args:
        name: Run name
    """
    set_run_name(name)


# ========== Convenience Functions ==========

def mark_as_critical(test_id: Optional[str] = None) -> None:
    """Mark test as critical severity."""
    set_severity("critical", test_id)


def mark_as_high(test_id: Optional[str] = None) -> None:
    """Mark test as high severity."""
    set_severity("high", test_id)


def mark_as_medium(test_id: Optional[str] = None) -> None:
    """Mark test as medium severity."""
    set_severity("medium", test_id)


def mark_as_low(test_id: Optional[str] = None) -> None:
    """Mark test as low severity."""
    set_severity("low", test_id)


def tag_as_smoke(test_id: Optional[str] = None) -> None:
    """Tag test as smoke test."""
    add_tag("smoke", test_id)


def tag_as_regression(test_id: Optional[str] = None) -> None:
    """Tag test as regression test."""
    add_tag("regression", test_id)


def tag_as_integration(test_id: Optional[str] = None) -> None:
    """Tag test as integration test."""
    add_tag("integration", test_id)


def tag_as_unit(test_id: Optional[str] = None) -> None:
    """Tag test as unit test."""
    add_tag("unit", test_id)


# ========== Context Information ==========

def get_current_test_id() -> Optional[str]:
    """Get the current test ID.
    
    Returns:
        Current test ID or None if not set
    """
    ctx = get_current_test_context()
    return ctx.test_id


def get_current_server_id() -> Optional[int]:
    """Get the current test's server-assigned ID.
    
    Returns:
        Server ID or None if not set
    """
    ctx = get_current_test_context()
    return ctx.server_id


def get_current_run_id() -> Optional[int]:
    """Get the current run's server-assigned ID.
    
    Returns:
        Run ID or None if not set
    """
    ctx = get_current_test_context()
    return ctx.run_id
