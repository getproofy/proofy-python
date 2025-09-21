"""Decorators for test metadata and attributes."""

from __future__ import annotations

from typing import Any

from proofy.core.models import ProofyAttributes
from proofy.hooks.manager import get_plugin_manager

_plugin_manager = get_plugin_manager()


def _dummy(result) -> Any:
    if result:
        return result[0]
    else:
        return lambda function: function


def attributes(**attributes: dict[str, str]) -> Any:
    return _dummy(_plugin_manager.hook.mark_attributes(attributes=attributes))


def name(name: str) -> Any:
    return attributes(**{ProofyAttributes.NAME.value: name})


def title(title: str) -> Any:
    return name(title)


def description(description: str) -> Any:
    return attributes(**{ProofyAttributes.DESCRIPTION.value: description})


def severity(level: str) -> Any:
    return attributes(**{ProofyAttributes.SEVERITY.value: level})
