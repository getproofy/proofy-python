"""Basic tests for pytest-proofy plugin."""

from datetime import datetime
from unittest.mock import Mock, patch

from pytest_proofy.config import ProofyConfig
from pytest_proofy.plugin import ProofyPytestPlugin


class TestProofyPytestPlugin:
    """Tests for ProofyPytestPlugin class."""

    def setup_method(self):
        """Setup test fixtures."""
        self.config = ProofyConfig(
            mode="lazy",
            api_base="https://api.example.com",
            token="test-token",
            project_id=123,
        )

    def test_plugin_initialization(self):
        """Test plugin initialization."""
        plugin = ProofyPytestPlugin(self.config)

        assert plugin.config == self.config
        assert plugin.client is not None
        assert plugin.run_id is None
        assert plugin.test_results == {}
        assert plugin.test_start_times == {}

    def test_plugin_without_api_config(self):
        """Test plugin initialization without API configuration."""
        config = ProofyConfig(mode="lazy")  # No API base or token
        plugin = ProofyPytestPlugin(config)

        assert plugin.client is None

    def test_get_test_id(self):
        """Test test ID generation."""
        plugin = ProofyPytestPlugin(self.config)

        mock_item = Mock()
        mock_item.nodeid = "tests/test_example.py::test_function"

        test_id = plugin._get_test_id(mock_item)
        assert test_id == "tests/test_example.py::test_function"

    def test_get_test_name_simple(self):
        """Test test name generation for simple test."""
        plugin = ProofyPytestPlugin(self.config)

        mock_item = Mock()
        mock_item.name = "test_function"
        mock_item.cls = None

        with patch("pytest_proofy.plugin.get_current_test_context") as mock_get_ctx:
            mock_get_ctx.return_value = None

            test_name = plugin._get_test_name(mock_item)
            assert test_name == "test_function"

    def test_get_test_name_with_class(self):
        """Test test name generation for class method."""
        plugin = ProofyPytestPlugin(self.config)

        mock_item = Mock()
        mock_item.name = "test_method"
        mock_item.cls = Mock()
        mock_item.cls.__name__ = "TestClass"

        with patch("pytest_proofy.plugin.get_current_test_context") as mock_get_ctx:
            mock_get_ctx.return_value = None

            test_name = plugin._get_test_name(mock_item)
            assert test_name == "TestClass::test_method"

    def test_get_test_name_with_context(self):
        """Test test name generation with context override."""
        plugin = ProofyPytestPlugin(self.config)

        mock_item = Mock()
        mock_item.name = "test_function"
        mock_item.cls = None

        mock_ctx = Mock()
        mock_ctx.name = "Custom Test Name"

        with patch("pytest_proofy.plugin.get_current_test_context") as mock_get_ctx:
            mock_get_ctx.return_value = mock_ctx

            test_name = plugin._get_test_name(mock_item)
            assert test_name == "Custom Test Name"

    def test_get_test_path(self):
        """Test test path generation."""
        plugin = ProofyPytestPlugin(self.config)

        mock_item = Mock()
        mock_item.fspath = "/project/tests/test_example.py"
        mock_item.config = Mock()
        mock_item.config.rootpath = "/project"

        test_path = plugin._get_test_path(mock_item).as_posix()
        assert test_path == "tests/test_example.py"

    def test_outcome_to_status_mapping(self):
        """Test outcome to status conversion."""
        plugin = ProofyPytestPlugin(self.config)

        from proofy import ResultStatus

        assert plugin._outcome_to_status("passed") == ResultStatus.PASSED
        assert plugin._outcome_to_status("failed") == ResultStatus.FAILED
        assert plugin._outcome_to_status("error") == ResultStatus.BROKEN
        assert plugin._outcome_to_status("skipped") == ResultStatus.SKIPPED
        assert plugin._outcome_to_status("unknown") == ResultStatus.BROKEN

    @patch("pytest_proofy.plugin.get_current_test_context")
    def test_create_test_result(self, mock_get_ctx):
        """Test test result creation."""
        plugin = ProofyPytestPlugin(self.config)

        # Setup mocks
        mock_item = Mock()
        mock_item.nodeid = "tests/test_example.py::test_function"
        mock_item.name = "test_function"
        mock_item.cls = None
        mock_item.fspath = "/project/tests/test_example.py"
        mock_item.config = Mock()
        mock_item.config.rootpath = "/project"
        mock_item.iter_markers.return_value = []

        mock_report = Mock()
        mock_report.outcome = "passed"
        mock_report.duration = 1.5
        mock_report.failed = False

        mock_ctx = Mock()
        mock_ctx.name = None  # No custom name
        mock_ctx.description = "Test description"
        mock_ctx.severity = "high"
        mock_ctx.tags = ["smoke"]
        mock_ctx.metadata = {"key": "value"}
        mock_ctx.attributes = {"attr": "val"}
        mock_ctx.files = []
        mock_get_ctx.return_value = mock_ctx

        # Set start time
        start_time = datetime.now()
        plugin.test_start_times["tests/test_example.py::test_function"] = start_time

        result = plugin._create_test_result(mock_item, mock_report)

        assert result.id == "tests/test_example.py::test_function"
        assert result.name == "test_function"
        assert result.path == "tests/test_example.py"
        assert result.outcome == "passed"
        assert result.duration_ms == 1500.0
        assert result.metadata["description"] == "Test description"
        assert result.metadata["severity"] == "high"
        assert result.metadata["key"] == "value"
        assert "smoke" in result.tags
        assert result.attributes["attr"] == "val"

    def test_create_test_result_with_error(self):
        """Test test result creation with error."""
        plugin = ProofyPytestPlugin(self.config)

        mock_item = Mock()
        mock_item.nodeid = "tests/test_example.py::test_function"
        mock_item.name = "test_function"
        mock_item.cls = None
        mock_item.fspath = "/project/tests/test_example.py"
        mock_item.config = Mock()
        mock_item.config.rootpath = "/project"
        mock_item.iter_markers.return_value = []

        mock_report = Mock()
        mock_report.outcome = "failed"
        mock_report.duration = 0.5
        mock_report.failed = True
        mock_report.longrepr = "AssertionError: test failed"

        with patch("pytest_proofy.plugin.get_current_test_context") as mock_get_ctx:
            mock_get_ctx.return_value = None

            result = plugin._create_test_result(mock_item, mock_report)

            assert result.outcome == "failed"
            assert result.message == "AssertionError: test failed"
            assert result.traceback == "AssertionError: test failed"


class TestPluginHooks:
    """Test pytest hook implementations."""

    def test_pytest_addoption(self):
        """Test that options are registered."""
        from pytest_proofy.plugin import pytest_addoption

        mock_parser = Mock()
        mock_parser.getgroup.return_value = Mock()

        pytest_addoption(mock_parser)

        # Verify getgroup was called
        mock_parser.getgroup.assert_called_once()

    @patch("pytest_proofy.plugin.ProofyPytestPlugin")
    @patch("pytest_proofy.plugin.resolve_options")
    def test_pytest_configure(self, mock_resolve, mock_plugin_class):
        """Test plugin configuration."""
        from pytest_proofy.plugin import pytest_configure

        mock_config = Mock()
        mock_proofy_config = Mock()
        mock_resolve.return_value = mock_proofy_config
        mock_plugin = Mock()
        mock_plugin_class.return_value = mock_plugin

        pytest_configure(mock_config)

        mock_resolve.assert_called_once_with(mock_config)
        mock_plugin_class.assert_called_once_with(mock_proofy_config)
        assert mock_config._proofy_plugin == mock_plugin
