"""Decorators for test metadata and attributes."""

from __future__ import annotations

from typing import Any

from proofy._internal.constants import PredefinedAttribute
from proofy._internal.hooks.manager import get_plugin_manager

_plugin_manager = get_plugin_manager()


def _dummy(result: Any) -> Any:
    if result:
        return result[0]
    else:
        return lambda function: function


def attributes(**attributes: dict[str, Any]) -> Any:
    # Delegate to framework-specific marker creation
    return _dummy(_plugin_manager.hook.proofy_mark_attributes(attributes=attributes))


def name(name: str) -> Any:
    # Plugin looks for 'name' to override display name
    return attributes(**{PredefinedAttribute.NAME.value: name})  # type: ignore[arg-type]


def title(title: str) -> Any:
    return name(title)


def description(description: str) -> Any:
    return attributes(**{PredefinedAttribute.DESCRIPTION.value: description})  # type: ignore[arg-type]


def severity(level: str) -> Any:
    return attributes(**{PredefinedAttribute.SEVERITY.value: level})  # type: ignore[arg-type]


def tags(*tags: str) -> Any:
    # Store under special key for pytest plugin to split into Result.tags
    return attributes(**{PredefinedAttribute.TAGS.value: list(tags)})  # type: ignore[arg-type]


__all__ = [
    "attributes",
    "description",
    "name",
    "severity",
    "tags",
    "title",
]
