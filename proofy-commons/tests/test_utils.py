"""Tests for core utility functions."""

from __future__ import annotations

import hashlib

from proofy.core.utils import generate_test_identifier


def test_generate_test_identifier_returns_16_char_string():
    """Test that generate_test_identifier returns a 16-character hex string."""
    identifier = generate_test_identifier("tests/test_file.py::TestClass::test_method")

    assert isinstance(identifier, str)
    assert len(identifier) == 16
    # Verify it's a valid hex string (only contains hex digits)
    assert all(c in "0123456789abcdef" for c in identifier)


def test_generate_test_identifier_is_deterministic():
    """Test that the same test_path always produces the same identifier."""
    test_path = "tests/test_file.py::TestClass::test_method"
    identifier1 = generate_test_identifier(test_path)
    identifier2 = generate_test_identifier(test_path)

    assert identifier1 == identifier2


def test_generate_test_identifier_matches_sha256():
    """Test that the identifier matches the expected SHA256 hash."""
    test_path = "tests/test_file.py::TestClass::test_method"
    expected_hash = hashlib.sha256(test_path.encode("utf-8")).hexdigest()[:16]

    identifier = generate_test_identifier(test_path)

    assert identifier == expected_hash


def test_generate_test_identifier_different_paths_different_ids():
    """Test that different test paths produce different identifiers."""
    path1 = "tests/test_file.py::TestClass::test_method1"
    path2 = "tests/test_file.py::TestClass::test_method2"

    id1 = generate_test_identifier(path1)
    id2 = generate_test_identifier(path2)

    assert id1 != id2


def test_generate_test_identifier_handles_special_chars():
    """Test that identifiers work with special characters in test names."""
    # Test with various special characters that might appear in test paths
    test_paths = [
        "tests/test_file.py::TestClass::test_method[param-value]",
        "tests/test_file.py::TestClass::test_method[param_value]",
        "tests/test_file.py::TestClass::test_method[param.value]",
        "tests/test_file.py::TestClass::test_method[param/value]",
    ]

    identifiers = [generate_test_identifier(path) for path in test_paths]

    # All should be valid hex strings
    for identifier in identifiers:
        assert len(identifier) == 16
        assert all(c in "0123456789abcdef" for c in identifier)

    # All should be different
    assert len(set(identifiers)) == len(identifiers)


def test_generate_test_identifier_with_parametrized_tests():
    """Test identifier generation for parametrized tests."""
    # Parametrized test with different parameters
    base_path = "tests/test_file.py::TestClass::test_method"
    param1 = f"{base_path}[param1]"
    param2 = f"{base_path}[param2]"

    id1 = generate_test_identifier(param1)
    id2 = generate_test_identifier(param2)

    # Different parameters should produce different identifiers
    assert id1 != id2

    # Both should be valid
    for identifier in [id1, id2]:
        assert len(identifier) == 16
        assert all(c in "0123456789abcdef" for c in identifier)


def test_generate_test_identifier_framework_formats():
    """Test that identifier works with different framework path formats."""
    # Demonstrate that the function works with different runner formats
    paths = [
        # pytest format
        "tests/test_file.py::TestClass::test_method",
        # unittest format
        "tests.test_file.TestClass.test_method",
        # nose2 format
        "tests.test_file:TestClass.test_method",
        # behave format (example)
        "features/login.feature:Scenario: User logs in",
    ]

    identifiers = [generate_test_identifier(path) for path in paths]

    # All should be valid hex strings
    for identifier in identifiers:
        assert len(identifier) == 16
        assert all(c in "0123456789abcdef" for c in identifier)

    # All should be different
    assert len(set(identifiers)) == len(identifiers)
