"""Unit and performance tests for limits utilities."""

from __future__ import annotations

import json

import pytest
from proofy._internal.results.limits import (
    ATTRIBUTE_KEY_LIMIT,
    ATTRIBUTE_VALUE_LIMIT,
    MESSAGE_LIMIT,
    NAME_LIMIT,
    clamp_attributes,
    clamp_string,
    limit_dict_strings,
    limit_list_strings,
)


def test_clamp_string_none_returns_none():
    """None input should remain None."""

    assert clamp_string(None, NAME_LIMIT) is None


def test_clamp_string_honours_limit(caplog: pytest.LogCaptureFixture):
    """Values longer than limit should be truncated and logged."""

    value = "x" * (NAME_LIMIT + 10)

    with caplog.at_level("DEBUG", logger="Proofy"):
        result = clamp_string(value, NAME_LIMIT, context="name")

    assert result == value[:NAME_LIMIT]
    assert any("Clamped name" in record.message for record in caplog.records)


def test_clamp_attributes_clamps_keys_and_values():
    """Long keys and string values are truncated to their respective limits."""

    key = "k" * (ATTRIBUTE_KEY_LIMIT + 5)
    value = "v" * (ATTRIBUTE_VALUE_LIMIT + 5)

    limited = clamp_attributes({key: value})

    assert list(limited.keys()) == [key[:ATTRIBUTE_KEY_LIMIT]]
    assert limited[key[:ATTRIBUTE_KEY_LIMIT]] == value[:ATTRIBUTE_VALUE_LIMIT]


def test_clamp_attributes_skips_duplicate_clamped_keys(
    caplog: pytest.LogCaptureFixture,
):
    """Attributes resolving to the same clamped key keep the first occurrence."""

    key_a = "a" * (ATTRIBUTE_KEY_LIMIT + 2)
    key_b = "a" * (ATTRIBUTE_KEY_LIMIT + 10)

    with caplog.at_level("DEBUG", logger="Proofy"):
        limited = clamp_attributes({key_a: "first", key_b: "second"})

    assert limited == {key_a[:ATTRIBUTE_KEY_LIMIT]: "first"}
    assert any("duplicates existing key" in record.message for record in caplog.records)


def test_limit_list_strings_respects_json_limit():
    """Lists should truncate when serialised length exceeds limit."""

    values = ["short", "another", "third"]
    limit = len(json.dumps(values[:2], ensure_ascii=False)) + 7  # Force truncation on third

    limited = limit_list_strings(values, limit=limit)

    assert limited == values[:2] + ["..."]


def test_limit_list_strings_handles_empty():
    """Empty lists return empty lists."""

    assert limit_list_strings([]) == []


def test_limit_dict_strings_truncates_and_marks_overflow():
    """Dicts should truncate and append overflow marker."""

    values = {"one": "a", "two": "b", "three": "c"}
    limit = len(json.dumps({"one": "a", "two": "b"}, ensure_ascii=False)) + 10

    limited = limit_dict_strings(values, limit=limit)

    assert limited["one"] == "a"
    assert limited["two"] == "b"
    assert limited["."] == "."


def test_limit_dict_strings_falls_back_to_repr_for_non_serialisable():
    """Non serialisable values should be coerced to repr for the limit check."""

    class NonSerializable:  # pragma: no cover - only used for repr string
        def __repr__(self) -> str:  # noqa: D401 - small repr method
            return "<NonSerializable>"

    values = {"key": NonSerializable()}

    limited = limit_dict_strings(values, limit=MESSAGE_LIMIT)

    assert limited == values
