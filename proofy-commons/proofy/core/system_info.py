"""System information collection utilities."""

from __future__ import annotations

import platform
import sys
from importlib import metadata
from importlib.metadata import PackageNotFoundError
from typing import Any

from proofy._internal.constants import PredefinedAttribute


def collect_system_attributes() -> dict[str, Any]:
    """Collect system information as run attributes.

    Returns:
        Dictionary with system information including:
        - Python version
        - Operating system
    """
    return {
        PredefinedAttribute.PYTHON_VERSION.value: f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        PredefinedAttribute.PLATFORM.value: platform.platform(),
    }


def get_framework_version(framework: str) -> str | None:
    """Get version of a testing framework.

    Args:
        framework: Name of the framework (e.g., 'pytest', 'unittest')

    Returns:
        Version string or None if not available
    """

    if framework == "unittest":
        # unittest is part of the standard library; we map to Python version.
        return f"{sys.version_info.major}.{sys.version_info.minor}"

    package_name = {
        "pytest": "pytest",
        "behave": "behave",
        "nose2": "nose2",
    }.get(framework)

    if not package_name:
        return None

    try:
        return metadata.version(package_name)
    except PackageNotFoundError:
        return None


__all__ = [
    "collect_system_attributes",
    "get_framework_version",
]
