from __future__ import annotations

from proofy._internal.hooks import get_plugin_manager, reset_plugin_manager
from pytest_proofy.plugin import PytestProofyHooks


def setup_function() -> None:
    # Ensure clean pluggy manager between tests
    reset_plugin_manager()


def teardown_function() -> None:
    reset_plugin_manager()


def test_hookspecs_registered_on_manager_creation() -> None:
    pm = get_plugin_manager()
    # pluggy exposes registered hook names via .hook
    assert hasattr(pm, "hook")
    # Ensure our expected hooks exist
    assert hasattr(pm.hook, "proofy_test_start")
    assert hasattr(pm.hook, "proofy_test_finish")
    assert hasattr(pm.hook, "proofy_mark_attributes")


def test_register_pytest_hooks_and_call_mark_attributes() -> None:
    pm = get_plugin_manager()
    hooks_impl = PytestProofyHooks()
    pm.register(hooks_impl, "pytest_proofy_hooks_test")

    # Mock pytest.mark.proofy_attributes since it's not registered in test environment
    from unittest.mock import patch

    import pytest as _pytest

    # Create a mock mark object
    mock_mark = type("MockMark", (), {"name": "proofy_attributes", "kwargs": {"k": "v"}})()

    # Patch the MarkGenerator object directly for cross-platform/pytest-version robustness
    with patch.object(_pytest.mark, "proofy_attributes", return_value=mock_mark):
        marker = pm.hook.proofy_mark_attributes(attributes={"k": "v"})
        # pluggy returns a list of results (one per implementation)
        assert isinstance(marker, list)
        assert marker, "Expected at least one hook implementation result"
        result = marker[0]
        # The plugin returns a pytest mark object
        assert hasattr(result, "name")
        assert result.name == "proofy_attributes"


def test_test_start_and_finish_hooks_are_callable() -> None:
    pm = get_plugin_manager()
    hooks_impl = PytestProofyHooks()
    pm.register(hooks_impl, "pytest_proofy_hooks_test")

    # proofy_test_start returns None; should call without exceptions
    pm.hook.proofy_test_start(
        test_id="node::id",
        test_name="test_name",
        test_path="tests/test_sample.py::test_name",
        metadata=None,
    )

    # proofy_test_finish should accept a TestResult; import from commons
    from proofy.core.models import ResultStatus, TestResult

    tr = TestResult(
        id="node::id",
        name="test_name",
        path="node::id",
        test_path="tests/test_sample.py",
        test_identifier="abc123456789",
        status=ResultStatus.PASSED,
    )
    pm.hook.proofy_test_finish(test_result=tr)
