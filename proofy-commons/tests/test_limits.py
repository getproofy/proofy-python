"""Unit and performance tests for limits utilities."""

from __future__ import annotations

import pytest
from proofy._internal.results.limits import (
    ATTRIBUTE_KEY_LIMIT,
    ATTRIBUTE_VALUE_LIMIT,
    NAME_LIMIT,
    clamp_attributes,
    clamp_string,
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


def test_clamp_string_with_suffix():
    """Suffix should be appended to the clamped value if the limit is exceeded."""

    value = "x" * 30

    result = clamp_string(value, 20, suffix="...")

    assert result == value[:17] + "..."
