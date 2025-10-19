"""Proofy Python Commons - Shared components for testing framework integrations."""

from __future__ import annotations

# Public API facade
from .core.api import (
    add_attachment,
    add_attributes,
    add_data,
    add_run_attributes,
    get_current_run_id,
    get_current_test_id,
    get_run_attributes,
    set_description,
    set_name,
    set_run_attribute,
    set_run_name,
    set_severity,
)
from .core.client import ArtifactType

# Decorators
from .core.decorators import (
    attributes,
    description,
    name,
    severity,
    title,
)
from .core.models import Severity

# Version info
__version__ = "0.1.1"
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
    "add_data",
    "add_attributes",
    "add_run_attributes",
    "get_current_run_id",
    "get_current_test_id",
    "get_run_attributes",
    "set_description",
    "set_name",
    "set_run_attribute",
    "set_run_name",
    "set_severity",
    # Decorators
    "name",
    "title",
    "description",
    "severity",
    "attributes",
    "ArtifactType",
    "Severity",
]
