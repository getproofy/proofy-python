"""Internal constants and enums for predefined Proofy attributes.

These keys are used across integrations to mark special metadata fields.
"""

from __future__ import annotations

from enum import Enum


class PredefinedAttribute(str, Enum):
    NAME = "__proofy_display_name"  # only used for display name, not sent to the server
    DESCRIPTION = "__proofy_description"
    SEVERITY = "severity"
    TAGS = "__proofy_tags"
    PARAMETERS = "__proofy_parameters"
    MARKERS = "__proofy_markers"

    FRAMEWORK = "__proofy_framework"
    FRAMEWORK_VERSION = "__proofy_framework_version"
    ERROR_MESSAGE = "__proofy_error_message"

    PYTHON_VERSION = "__proofy_python_version"
    PLATFORM = "__proofy_platform"


__all__ = [
    "PredefinedAttribute",
]
