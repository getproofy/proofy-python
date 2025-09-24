"""Proofy Python Commons - Shared components for testing framework integrations."""

from __future__ import annotations

# Public API facade
from proofy.core.api import (
    add_attachment,
    add_attributes,
    add_tag,
    add_tags,
    get_current_run_id,
    get_current_test_id,
    set_description,
    set_name,
    set_title,
    set_run_name,
    set_severity,
)

# Decorators
from proofy.core.decorators import (
    attributes,
    description,
    name,
    severity,
    title,
    tags,
)

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
    # Public API
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
    # Decorators
    "name",
    "title",
    "description",
    "severity",
    "tags",
    "attributes",
]
