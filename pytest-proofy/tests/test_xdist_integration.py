"""Tests for pytest-xdist integration."""

from unittest.mock import Mock, patch

from pytest_proofy.config import ProofyConfig
from pytest_proofy.plugin import ProofyPytestPlugin, pytest_sessionstart
from pytest_proofy.xdist_support import is_xdist_worker, setup_worker_plugin


class TestXdistIntegration:
    """Test xdist integration functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.config = ProofyConfig(
            mode="batch",
            api_base="https://api.example.com",
            token="test-token",
            project_id=123,
        )

    def test_xdist_worker_detection(self):
        """Test xdist worker detection."""
        # Test non-worker session
        mock_session = Mock()
        mock_session.config = Mock(spec=[])  # No workerinput

        assert not is_xdist_worker(mock_session)

        # Test worker session
        mock_worker_session = Mock()
        mock_worker_session.config = Mock()
        mock_worker_session.config.workerinput = {}

        assert is_xdist_worker(mock_worker_session)

    def test_worker_session_initialization(self):
        """Test worker session initialization with transferred config."""
        # Mock session with workerinput (simulating worker)
        mock_session = Mock()
        mock_session.config = Mock()
        mock_session.config.workerinput = {
            "proofy_config_dict": self.config.__dict__,
            "proofy_run_id": 42,
            "proofy_session_id": "test-session-123",
        }

        plugin = setup_worker_plugin(mock_session)

        # Verify plugin was created with transferred config
        assert plugin is not None
        assert plugin.config.mode == self.config.mode
        assert plugin.config.api_base == self.config.api_base

        # Verify run_id and session_id were set from transfer
        assert plugin.run_id == 42
        assert plugin.session_id == "test-session-123"

    def test_master_session_initialization(self):
        """Test master session initialization (no workerinput)."""
        mock_session = Mock()
        mock_session.config = Mock(spec=[])  # No workerinput attribute

        mock_plugin = Mock()
        mock_plugin.config = self.config
        mock_plugin.run_id = None

        with patch("pytest_proofy.plugin._plugin_instance", mock_plugin):
            mock_plugin._create_run.return_value = 42

            pytest_sessionstart(mock_session)

            # Verify run was created on master
            mock_plugin._create_run.assert_called_once_with(mock_session)
            assert mock_plugin.run_id == 42

    def test_worker_session_no_run_creation(self):
        """Test that workers don't create runs."""
        mock_session = Mock()
        mock_session.config = Mock()
        mock_session.config.workerinput = {
            "proofy_config_dict": self.config.__dict__,
            "proofy_run_id": 42,
            "proofy_session_id": "test-session-123",
        }

        with (
            patch("pytest_proofy.plugin._plugin_instance", None),
            patch("pytest_proofy.plugin.ProofyPytestPlugin") as mock_plugin_class,
        ):
            mock_plugin = Mock()
            mock_plugin.config = self.config
            mock_plugin_class.return_value = mock_plugin

            pytest_sessionstart(mock_session)

            # Verify _create_run was not called (worker shouldn't create runs)
            mock_plugin._create_run.assert_not_called()

    def test_session_finish_worker_vs_master(self):
        """Test session finish behavior differs between worker and master."""
        from pytest_proofy.plugin import pytest_sessionfinish

        # Test worker behavior
        mock_worker_session = Mock()
        mock_worker_session.config = Mock()
        mock_worker_session.config.workerinput = {}  # Has workerinput = worker

        mock_plugin = Mock()
        mock_plugin.config = self.config
        mock_plugin.config.always_backup = True  # Enable backup
        mock_plugin.client = None  # No client to trigger backup
        mock_plugin.results_handler = Mock()

        with patch("pytest_proofy.plugin._plugin_instance", mock_plugin):
            pytest_sessionfinish(mock_worker_session, 0)

            # Worker should not finalize run
            mock_plugin._finalize_run.assert_not_called()
            # But should backup results via handler (merge only on master)
            assert mock_plugin.results_handler.backup_results.called

        # Reset the mock for master test
        mock_plugin.reset_mock()

        # Test master behavior
        mock_master_session = Mock()
        mock_master_session.config = Mock(spec=[])  # No workerinput = master

        with patch("pytest_proofy.plugin._plugin_instance", mock_plugin):
            pytest_sessionfinish(mock_master_session, 0)

            # Master should finalize run
            mock_plugin._finalize_run.assert_called_once()
            # And backup results via handler, with merge on master
            assert mock_plugin.results_handler.backup_results.called
            assert mock_plugin.results_handler.merge_worker_results.called


class TestXdistWorkerCoordination:
    """Test worker coordination scenarios."""

    def test_multiple_workers_same_run_id(self):
        """Test multiple workers using same run_id."""
        shared_run_id = 42
        shared_session_id = "shared-session-123"

        config_dict = ProofyConfig(
            mode="live",
            api_base="https://api.example.com",
            token="test-token",
            project_id=123,
        ).__dict__

        # Simulate two workers
        for _ in ["worker1", "worker2"]:
            mock_session = Mock()
            mock_session.config = Mock()
            mock_session.config.workerinput = {
                "proofy_config_dict": config_dict,
                "proofy_run_id": shared_run_id,
                "proofy_session_id": shared_session_id,
            }

            with (
                patch("pytest_proofy.plugin._plugin_instance", None),
                patch("pytest_proofy.plugin.ProofyPytestPlugin") as mock_plugin_class,
            ):
                mock_plugin = Mock()
                mock_plugin_class.return_value = mock_plugin

                pytest_sessionstart(mock_session)

                # Both workers should use same run_id
                assert mock_plugin.run_id == shared_run_id
                assert mock_plugin.session_id == shared_session_id

    def test_worker_result_isolation(self):
        """Test that worker results are isolated."""
        # Create two plugin instances (simulating two workers)
        config = ProofyConfig(mode="lazy")

        worker1_plugin = ProofyPytestPlugin(config)
        worker2_plugin = ProofyPytestPlugin(config)

        # Add results to each worker
        from proofy import TestResult

        result1 = TestResult(id="test1", name="Test 1", path="test1.py", run_id=42)
        result2 = TestResult(id="test2", name="Test 2", path="test2.py", run_id=42)

        assert worker1_plugin.results_handler is not None
        assert worker2_plugin.results_handler is not None
        worker1_plugin.results_handler.on_test_finished(result1)
        worker2_plugin.results_handler.on_test_finished(result2)

        # Verify isolation
        assert any(r.id == "test1" for r in worker1_plugin.results_handler._results)
        assert not any(r.id == "test2" for r in worker1_plugin.results_handler._results)

        assert any(r.id == "test2" for r in worker2_plugin.results_handler._results)
        assert not any(r.id == "test1" for r in worker2_plugin.results_handler._results)

    def test_node_hooks_called(self):
        """Test that xdist node hooks are properly handled."""
        # Test that xdist support module exists and works
        from pytest_proofy.xdist_support import XDIST_AVAILABLE, register_xdist_hooks

        # Should be a boolean
        assert isinstance(XDIST_AVAILABLE, bool)

        # Should be able to call register function
        mock_plugin_manager = Mock()
        mock_plugin_instance = Mock()

        # Should not raise exceptions
        register_xdist_hooks(mock_plugin_manager, mock_plugin_instance)


class TestXdistResultHandling:
    """Test result handling in xdist environment."""

    def test_live_mode_worker_results(self):
        """Test live mode result handling in worker."""
        config = ProofyConfig(
            mode="live",
            api_base="https://api.example.com",
            token="test-token",
        )

        plugin = ProofyPytestPlugin(config)
        plugin.run_id = 42

        # Mock client
        mock_client = Mock()
        mock_client.create_test_result.return_value = 1001
        plugin.client = mock_client

        # Create test result
        from proofy import ResultStatus, TestResult

        result = TestResult(
            id="test1",
            name="Test 1",
            path="test1.py",
            run_id=42,
            status=ResultStatus.PASSED,
            outcome="passed",  # Need outcome to trigger update
        )

        # Send result in live mode
        plugin._send_result_live(result)

        # Verify client was called
        mock_client.create_test_result.assert_called_once()
        mock_client.update_test_result.assert_called_once()

    def test_batch_mode_worker_results(self):
        """Test batch mode result collection in worker."""
        config = ProofyConfig(mode="batch")
        plugin = ProofyPytestPlugin(config)

        # Mock client
        mock_client = Mock()
        plugin.client = mock_client

        # Add multiple results
        from proofy import TestResult

        results = []
        for i in range(3):
            result = TestResult(id=f"test{i}", name=f"Test {i}", path=f"test{i}.py", run_id=42)
            assert plugin.results_handler is not None
            plugin.results_handler.on_test_finished(result)
            results.append(result)

        # Simulate session finish
        mock_session = Mock()
        mock_session.config = Mock()
        mock_session.config.workerinput = {}  # Worker session

        from pytest_proofy.plugin import pytest_sessionfinish

        with (
            patch("pytest_proofy.plugin._plugin_instance", plugin),
            patch("pytest_proofy.plugin.ResultsHandler.backup_results"),
            patch("pytest_proofy.plugin.ResultsHandler.merge_worker_results"),
        ):
            pytest_sessionfinish(mock_session, 0)

        # Verify batch send was called
        mock_client.send_test_results.assert_called_once()
        sent_results = mock_client.send_test_results.call_args[0][0]
        assert len(sent_results) == 3

    def test_config_serialization_deserialization(self):
        """Test config can be serialized and deserialized for workers."""
        original_config = ProofyConfig(
            mode="live",
            api_base="https://api.example.com",
            token="test-token",
            project_id=123,
            batch_size=50,
            enable_attachments=True,
            enable_hooks=False,
            timeout_s=30.0,
            max_retries=5,
            retry_delay=2.0,
        )

        # Serialize to dict (what happens in pytest_configure_node)
        config_dict = original_config.__dict__

        # Deserialize (what happens in worker pytest_sessionstart)
        reconstructed_config = ProofyConfig(**config_dict)

        # Verify all fields are preserved
        assert reconstructed_config.mode == original_config.mode
        assert reconstructed_config.api_base == original_config.api_base
        assert reconstructed_config.token == original_config.token
        assert reconstructed_config.project_id == original_config.project_id
        assert reconstructed_config.batch_size == original_config.batch_size
        assert reconstructed_config.enable_attachments == original_config.enable_attachments
        assert reconstructed_config.enable_hooks == original_config.enable_hooks
        assert reconstructed_config.timeout_s == original_config.timeout_s
        assert reconstructed_config.max_retries == original_config.max_retries
        assert reconstructed_config.retry_delay == original_config.retry_delay
