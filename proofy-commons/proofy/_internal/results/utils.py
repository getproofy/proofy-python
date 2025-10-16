import json
from typing import Any

from ...core.models import TestResult
from .limits import clamp_attributes, limit_dict_strings, limit_list_strings


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
        tags = limit_list_strings(result.tags)
        merged.update({"__proofy_tags": json.dumps(tags)})

    if result.parameters:
        parameters = limit_dict_strings(result.parameters)
        merged.update({"__proofy_parameters": json.dumps(parameters)})

    if result.markers:
        markers = limit_list_strings(result.markers)
        merged.update({"__proofy_markers": json.dumps(markers)})

    return merged
