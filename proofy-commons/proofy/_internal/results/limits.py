"""Utilities for enforcing Proofy payload limits."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

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
    suffix: str | None = None,
) -> str | None:
    """Clamp *value* to *limit* characters when possible. If *suffix* is provided, it will be appended to the clamped value if the limit is exceeded."""

    if value is None:
        return None
    if len(value) <= limit:
        return value

    if suffix:
        limit -= len(suffix)
    if limit < 0:
        return suffix
    clamped = value[:limit] + (suffix or "")
    label = context or "string"
    logger.debug("Clamped %s from %d to %d characters", label, len(value), limit)
    return clamped


def clamp_attributes(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    """Clamp attribute keys and string values to their limits."""

    if not attributes:
        return {}

    limited: dict[str, Any] = {}
    for key, value in attributes.items():
        # Keys must be strings for downstream serialization
        key_str = str(key)
        clamped_key = clamp_string(key_str, ATTRIBUTE_KEY_LIMIT, context="attribute key")
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
