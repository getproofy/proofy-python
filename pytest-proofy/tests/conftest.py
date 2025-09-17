"""Test configuration and fixtures for pytest-proofy tests."""

from unittest.mock import Mock

import pytest
from pytest_proofy.config import ProofyConfig


@pytest.fixture
def proofy_config():
    """Provide a basic ProofyConfig for testing."""
    return ProofyConfig(
        mode="lazy",
        api_base="https://api.example.com",
        token="test-token",
        project_id=123,
        batch_size=10,
        enable_attachments=True,
        enable_hooks=True,
    )


@pytest.fixture
def mock_pytest_item():
    """Provide a mock pytest Item."""
    item = Mock()
    item.nodeid = "tests/test_example.py::TestClass::test_method"
    item.name = "test_method"
    item.cls = Mock()
    item.cls.__name__ = "TestClass"
    item.fspath = "/project/tests/test_example.py"
    item.config = Mock()
    item.config.rootpath = "/project"
    item.iter_markers.return_value = []
    return item


@pytest.fixture
def mock_pytest_report():
    """Provide a mock pytest TestReport."""
    report = Mock()
    report.outcome = "passed"
    report.duration = 1.0
    report.failed = False
    report.longrepr = None
    return report


@pytest.fixture
def mock_proofy_client():
    """Provide a mock ProofyClient."""
    client = Mock()
    client.create_test_run.return_value = {"id": 42}
    client.create_test_result.return_value = 1001
    client.update_test_result.return_value = None
    client.send_test_result.return_value = Mock()
    client.send_test_results.return_value = Mock()
    return client
