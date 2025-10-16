"""Utility helpers for pytest Proofy integration."""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

MARKERS_JSON_LIMIT = 100
PARAMETERS_JSON_LIMIT = 100

logger = logging.getLogger("ProofyPytestPlugin")


def limit_markers(markers: list[str]) -> list[str]:
    """Clamp marker payload to the configured JSON length limit."""

    if not markers:
        return []

    limited: list[str] = []
    for marker in markers:
        candidate = limited + [marker]
        if len(json.dumps(candidate, ensure_ascii=False)) <= MARKERS_JSON_LIMIT:
            limited.append(marker)
        else:
            break

    if len(limited) < len(markers):
        logger.debug(
            "Truncated markers from %d to %d entries to satisfy %d-byte JSON limit",
            len(markers),
            len(limited),
            MARKERS_JSON_LIMIT,
        )
        candidate = limited + ["..."]
        if len(json.dumps(candidate, ensure_ascii=False)) <= MARKERS_JSON_LIMIT:
            limited.append("...")

    return limited


def limit_parameters(raw_params: Mapping[str, Any] | None) -> dict[str, Any]:
    """Clamp parameter payload to the configured JSON length limit."""

    if not raw_params:
        return {}

    parameters: dict[str, Any] = {}
    truncated = False

    for param_key, param_value in raw_params.items():
        candidate_value = param_value
        try:
            json.dumps(candidate_value, ensure_ascii=False)
        except Exception:
            candidate_value = repr(param_value)

        candidate_parameters = dict(parameters)
        candidate_parameters[param_key] = candidate_value
        if len(json.dumps(candidate_parameters, ensure_ascii=False)) <= PARAMETERS_JSON_LIMIT:
            parameters = candidate_parameters
        else:
            truncated = True
            break

    if truncated:
        logger.debug(
            "Truncated parameters from %d entries to satisfy %d-byte JSON limit",
            len(raw_params),
            len(parameters),
            PARAMETERS_JSON_LIMIT,
        )
        for ellipsis_key in ("...", "__truncated__"):
            candidate_parameters = dict(parameters)
            candidate_parameters[ellipsis_key] = True
            if len(json.dumps(candidate_parameters, ensure_ascii=False)) <= PARAMETERS_JSON_LIMIT:
                parameters = candidate_parameters
                break

    return parameters
