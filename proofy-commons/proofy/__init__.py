"""Proofy Python Commons - Shared components for testing framework integrations."""

from __future__ import annotations

# Core components
from .core.client import ProofyClient
from .core.models import (
    Attachment,
    FixtureResult,
    ProofyAttributes,
    Property,
    ResultStatus,
    RunStatus,
    TestResult,
)

# Hook system
from .hooks.manager import ProofyPluginManager, get_plugin_manager
from .hooks.specs import hookimpl, hookspec

# Runtime API
from .runtime.api import (
    add_attachment,
    add_attributes,
    add_file,
    add_metadata,
    add_run_name,  # Legacy compatibility
    add_tag,
    add_tags,
    get_current_run_id,
    get_current_server_id,
    get_current_test_id,
    mark_as_critical,
    mark_as_high,
    mark_as_low,
    mark_as_medium,
    set_description,
    set_name,
    set_run_name,
    set_severity,
    tag_as_integration,
    tag_as_regression,
    tag_as_smoke,
    tag_as_unit,
    upload_file,  # Legacy compatibility
)

# Context management
from .runtime.context import (
    SessionContext,
    TestContext,
    get_current_session_context,
    get_current_test_context,
    set_current_session_context,
    set_current_test_context,
)

# Decorators
from .runtime.decorators import (
    attributes,
    critical,
    description,
    high,
    integration,
    low,
    marker,
    medium,
    name,
    regression,
    severity,
    smoke,
    tags,
    title,
    unit,
)

# Version info
__version__ = "0.1.0"
__author__ = "Proofy Team"
__email__ = "team@proofy.io"

# Public API
__all__ = [
    # Version
    "__version__",
    "__author__",
    "__email__",
    # Core models and enums
    "TestResult",
    "Attachment",
    "FixtureResult",
    "Property",
    "ResultStatus",
    "RunStatus",
    "ProofyAttributes",
    # Client
    "ProofyClient",
    # Hook system
    "hookspec",
    "hookimpl",
    "get_plugin_manager",
    "ProofyPluginManager",
    # Context management
    "TestContext",
    "SessionContext",
    "get_current_test_context",
    "set_current_test_context",
    "get_current_session_context",
    "set_current_session_context",
    # Runtime API - Metadata
    "set_name",
    "set_description",
    "set_severity",
    "add_metadata",
    "add_attributes",
    "add_tag",
    "add_tags",
    # Runtime API - Attachments
    "add_attachment",
    "add_file",
    # Runtime API - Run management
    "set_run_name",
    # Runtime API - Context info
    "get_current_test_id",
    "get_current_server_id",
    "get_current_run_id",
    # Runtime API - Convenience
    "mark_as_critical",
    "mark_as_high",
    "mark_as_medium",
    "mark_as_low",
    "tag_as_smoke",
    "tag_as_regression",
    "tag_as_integration",
    "tag_as_unit",
    # Runtime API - Legacy compatibility
    "add_run_name",
    "upload_file",
    # Decorators
    "name",
    "title",
    "description",
    "severity",
    "tags",
    "attributes",
    "marker",
    # Decorator convenience
    "critical",
    "high",
    "medium",
    "low",
    "smoke",
    "regression",
    "integration",
    "unit",
]
