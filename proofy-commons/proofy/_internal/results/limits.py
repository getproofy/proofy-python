"""Utilities for enforcing Proofy payload limits."""

from __future__ import annotations

import json
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
) -> str | None:
    """Clamp *value* to *limit* characters when possible."""

    if value is None:
        return None
    if len(value) <= limit:
        return value

    clamped = value[:limit]
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


def limit_list_strings(values: list[str], *, limit: int = ATTRIBUTE_VALUE_LIMIT) -> list[str]:
    """Clamp marker payload to the configured JSON length limit."""

    if not values:
        return []

    limited: list[str] = []
    for value in values:
        candidate = limited + [value]
        if len(json.dumps(candidate, ensure_ascii=False)) <= limit:
            limited.append(value)
        else:
            break

    if len(limited) < len(values):
        logger.debug(
            "Truncated values from %d to %d entries to satisfy %d-byte JSON limit",
            len(values),
            len(limited),
            limit,
        )
        candidate = limited + ["..."]
        if len(json.dumps(candidate, ensure_ascii=False)) <= limit:
            limited.append("[...]")

    return limited


def limit_dict_strings(
    values: Mapping[str, Any] | None, *, limit: int = ATTRIBUTE_VALUE_LIMIT
) -> dict[str, Any]:
    """Clamp dictionary of strings to the configured JSON length limit."""

    if not values:
        return {}

    limited: dict[str, Any] = {}

    for key, value in values.items():
        candidate_value = value
        try:
            json.dumps(candidate_value, ensure_ascii=False)
        except Exception:
            candidate_value = repr(value)

        candidate = dict(limited)
        candidate[key] = candidate_value
        if len(json.dumps(candidate, ensure_ascii=False)) <= limit:
            limited[key] = value
        else:
            break

    if len(limited) < len(values):
        logger.debug(
            "Truncated values from %d to %d entries to satisfy %d-byte JSON limit",
            len(values),
            len(limited),
            limit,
        )
        candidate = dict(limited)
        candidate["..."] = "..."
        if len(json.dumps(candidate, ensure_ascii=False)) <= limit:
            limited = candidate

    return limited
