"""Utilities for enforcing Proofy payload limits."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:  # pragma: no cover - only used for typing
    from proofy.core.models import TestResult

PATH_LIMIT = 1024
NAME_LIMIT = 300
ATTRIBUTE_KEY_LIMIT = 65
ATTRIBUTE_VALUE_LIMIT = 256
MESSAGE_LIMIT = 64 * 1024

logger = logging.getLogger("Proofy")


def clamp_string(
    value: str | None,
    limit: int,
    *,
    context: str | None = None,
) -> str | None:
    """Clamp *value* to *limit* characters when possible."""

    if value is None:
        return None
    if len(value) <= limit:
        return value

    clamped = value[:limit]
    label = context or "string"
    logger.debug(
        "Clamped %s from %d to %d characters", label, len(value), limit
    )
    return clamped


def clamp_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    """Clamp attribute keys and string values to their limits."""

    if not attributes:
        return {}

    limited: dict[str, Any] = {}
    for key, value in attributes.items():
        # Keys must be strings for downstream serialization
        key_str = str(key)
        clamped_key = clamp_string(
            key_str, ATTRIBUTE_KEY_LIMIT, context="attribute key"
        )
        if not clamped_key:
            continue
        if clamped_key in limited:
            # Preserve the first occurrence when keys collide after clamping
            if clamped_key != key_str:
                logger.debug(
                    "Skipping attribute %r because clamped key %r duplicates existing key",
                    key_str,
                    clamped_key,
                )
            continue

        if isinstance(value, str):
            limited_value: Any = clamp_string(
                value,
                ATTRIBUTE_VALUE_LIMIT,
                context=f"attribute value for key {clamped_key!r}",
            )
        else:
            limited_value = value

        limited[clamped_key] = limited_value

    return limited


def apply_result_limits(result: "TestResult") -> None:
    """Clamp TestResult fields to the configured limits in-place."""

    result.path = clamp_string(result.path, PATH_LIMIT, context="result.path") or ""
    result.name = clamp_string(result.name, NAME_LIMIT, context="result.name") or ""
    result.attributes = clamp_attributes(result.attributes)

    if result.message is not None:
        result.message = clamp_string(
            result.message, MESSAGE_LIMIT, context="result.message"
        )

    if result.tags:
        result.tags = [tag for tag in result.tags if isinstance(tag, str)]

