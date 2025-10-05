"""Tests for run attributes functionality."""

from __future__ import annotations

import pytest
from proofy._impl.context.backend import ThreadLocalBackend
from proofy._impl.context.service import ContextService
from proofy.core.system_info import collect_system_attributes, get_framework_version


@pytest.fixture
def context_service():
    """Provide a fresh context service for each test."""
    return ContextService(ThreadLocalBackend())


def test_set_run_attribute(context_service: ContextService):
    """Test setting individual run attribute."""
    session = context_service.start_session()

    context_service.set_run_attribute("environment", "production")

    assert session.run_attributes["environment"] == "production"


def test_add_run_attributes(context_service: ContextService):
    """Test adding multiple run attributes."""
    session = context_service.start_session()

    context_service.add_run_attributes(environment="staging", version="1.2.3", build_id="456")

    assert session.run_attributes["environment"] == "staging"
    assert session.run_attributes["version"] == "1.2.3"
    assert session.run_attributes["build_id"] == "456"


def test_get_run_attributes(context_service: ContextService):
    """Test getting all run attributes."""
    context_service.start_session()

    context_service.add_run_attributes(key1="value1", key2="value2")

    attrs = context_service.get_run_attributes()

    assert attrs["key1"] == "value1"
    assert attrs["key2"] == "value2"
    assert len(attrs) == 2


def test_run_attributes_without_session(context_service: ContextService):
    """Test that run attribute methods handle missing session gracefully."""
    # No session started

    context_service.set_run_attribute("key", "value")  # Should not raise
    attrs = context_service.get_run_attributes()  # Should return empty dict

    assert attrs == {}


def test_run_attributes_override(context_service: ContextService):
    """Test that later attributes override earlier ones."""
    context_service.start_session()

    context_service.set_run_attribute("environment", "dev")
    context_service.set_run_attribute("environment", "production")

    attrs = context_service.get_run_attributes()
    assert attrs["environment"] == "production"


def test_collect_system_attributes():
    """Test that system attributes are collected."""
    attrs = collect_system_attributes()

    # Check that all expected attributes are present
    assert "__proofy_python_version" in attrs
    assert "__proofy_platform" in attrs

    # Check that values are non-empty strings
    for _key, value in attrs.items():
        assert isinstance(value, str)
        assert len(value) > 0


def test_get_framework_version_pytest():
    """Test getting pytest version."""
    version = get_framework_version("pytest")

    assert version is not None
    assert isinstance(version, str)
    assert len(version) > 0


def test_get_framework_version_unknown():
    """Test getting version of unknown framework."""
    version = get_framework_version("unknown_framework")

    assert version is None


def test_public_api_integration(context_service: ContextService):
    """Test run attributes through public API.

    Note: This test uses the public API but with an isolated context service
    to avoid conflicts with the pytest-proofy plugin.
    """
    # Start session in our isolated service
    context_service.start_session()

    # Test methods directly on service (simulating public API)
    context_service.set_run_attribute("test_key", "test_value")
    context_service.add_run_attributes(api_test="true", environment="test")

    attrs = context_service.get_run_attributes()

    assert attrs["test_key"] == "test_value"
    assert attrs["api_test"] == "true"
    assert attrs["environment"] == "test"

    # Cleanup
    context_service.end_session()


def test_run_attributes_in_session_context(context_service: ContextService):
    """Test that run attributes persist in session context."""
    session1 = context_service.start_session()

    context_service.add_run_attributes(persistent_key="persistent_value")

    # Verify via session context
    assert session1.run_attributes["persistent_key"] == "persistent_value"

    # Verify via getter
    attrs = context_service.get_run_attributes()
    assert attrs["persistent_key"] == "persistent_value"
