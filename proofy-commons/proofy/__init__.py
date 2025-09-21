"""Proofy Python Commons - Shared components for testing framework integrations."""

from __future__ import annotations

# Public API facade (delegates to runtime API for now)
from proofy.api import (
    add_attachment,
    add_attributes,
    add_metadata,
    add_tag,
    add_tags,
    get_current_run_id,
    get_current_server_id,
    get_current_test_id,
)

# Core components
from proofy.core.client import ProofyClient, now_rfc3339
from proofy.core.models import (
    Attachment,
    FixtureResult,
    ProofyAttributes,
    ResultStatus,
    RunStatus,
    TestResult,
)

# Decorators
from proofy.decorators import (
    attributes,
    description,
    name,
    severity,
    title,
)

# Hook system
from proofy.hooks.manager import ProofyPluginManager, get_plugin_manager
from proofy.hooks.specs import hookimpl, hookspec
from proofy.utils import format_datetime_rfc3339

# Version info
__version__ = "0.1.0"
__author__ = "Proofy Team"
__email__ = "team@proofy.dev"

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
    "ResultStatus",
    "RunStatus",
    "ProofyAttributes",
    # Client
    "ProofyClient",
    "format_datetime_rfc3339",
    "now_rfc3339",
    # Hook system
    "hookspec",
    "hookimpl",
    "get_plugin_manager",
    "ProofyPluginManager",
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
    # Runtime API - Run management
    "set_run_name",
    # Runtime API - Context info
    "get_current_test_id",
    "get_current_server_id",
    "get_current_run_id",
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
]
