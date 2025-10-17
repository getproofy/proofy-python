import json
from typing import Any

from ...core.models import TestResult
from .limits import ATTRIBUTE_VALUE_LIMIT, clamp_attributes, clamp_string


def merge_metadata(result: TestResult) -> dict[str, Any]:
    """Merge all metadata sources into unified dict."""
    merged = {}

    # Start with metadata
    merged.update(result.metadata)

    # Add attributes
    if result.attributes:
        attributes = clamp_attributes(result.attributes)
        merged.update(attributes)

    if result.tags:
        tags = clamp_string(json.dumps(result.tags), ATTRIBUTE_VALUE_LIMIT, suffix=" ...")
        merged.update({"__proofy_tags": tags})

    if result.parameters:
        parameters = clamp_string(
            json.dumps(result.parameters), ATTRIBUTE_VALUE_LIMIT, suffix=" ..."
        )
        merged.update({"__proofy_parameters": parameters})

    if result.markers:
        markers = clamp_string(json.dumps(result.markers), ATTRIBUTE_VALUE_LIMIT, suffix=" ...")
        merged.update({"__proofy_markers": markers})

    return merged
