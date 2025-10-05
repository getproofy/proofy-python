"""System information collection utilities."""

from __future__ import annotations

import platform
import sys
from typing import Any


def collect_system_attributes() -> dict[str, Any]:
    """Collect system information as run attributes.

    Returns:
        Dictionary with system information including:
        - Python version
        - Operating system
    """
    return {
        "__proofy_python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "__proofy_platform": platform.platform(),
    }


def get_framework_version(framework: str) -> str | None:
    """Get version of a testing framework.

    Args:
        framework: Name of the framework (e.g., 'pytest', 'unittest')

    Returns:
        Version string or None if not available
    """
    try:
        if framework == "pytest":
            import pytest

            return pytest.__version__
        elif framework == "unittest":
            # unittest is built-in, use Python version
            return f"{sys.version_info.major}.{sys.version_info.minor}"
        elif framework == "behave":
            import behave

            return behave.__version__
        elif framework == "nose2":
            import nose2

            return nose2.__version__
    except (ImportError, AttributeError):
        return None
    return None


__all__ = [
    "collect_system_attributes",
    "get_framework_version",
]
