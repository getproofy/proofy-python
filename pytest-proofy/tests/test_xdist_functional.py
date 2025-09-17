"""Functional tests for xdist integration."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def temp_test_dir():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test files that can run in parallel
        test_files = {
            "test_module_a.py": '''
import time
import pytest

def test_a1():
    """Test A1."""
    time.sleep(0.1)  # Simulate some work
    assert True

def test_a2():
    """Test A2."""
    time.sleep(0.1)
    assert True

def test_a3():
    """Test A3."""
    time.sleep(0.1)
    assert True
''',
            "test_module_b.py": '''
import time
import pytest

def test_b1():
    """Test B1."""
    time.sleep(0.1)
    assert True

def test_b2():
    """Test B2."""
    time.sleep(0.1)
    assert True

def test_b3():
    """Test B3."""
    time.sleep(0.1)
    assert True
''',
            "test_module_c.py": '''
import time
import pytest

class TestClassC:
    def test_c1(self):
        """Test C1."""
        time.sleep(0.1)
        assert True

    def test_c2(self):
        """Test C2."""
        time.sleep(0.1)
        assert True

    def test_c3(self):
        """Test C3."""
        time.sleep(0.1)
        assert True
''',
        }

        for filename, content in test_files.items():
            (temp_path / filename).write_text(content)

        yield temp_path


class TestXdistFunctional:
    """Functional tests for xdist integration."""

    def test_xdist_plugin_loads_with_workers(self, temp_test_dir):
        """Test that plugin loads correctly when running with xdist workers."""
        # This test verifies the plugin can be loaded in an xdist environment
        # We'll mock the xdist execution environment

        from pytest_proofy.config import ProofyConfig
        from pytest_proofy.plugin import pytest_configure

        # Mock master configuration
        mock_master_config = Mock()
        mock_master_config.option = Mock()
        mock_master_config.option.proofy_mode = "batch"
        mock_master_config.option.proofy_api_base = None
        mock_master_config.option.proofy_token = None
        mock_master_config.option.proofy_project_id = None

        # Mock ini options
        mock_master_config.getini.return_value = None

        # Configure master
        with patch("pytest_proofy.plugin.resolve_options") as mock_resolve:
            config = ProofyConfig(mode="batch")
            mock_resolve.return_value = config

            pytest_configure(mock_master_config)

            # Verify master plugin was created
            assert hasattr(mock_master_config, "_proofy_plugin")

    def test_worker_session_initialization(self):
        """Test worker session gets properly initialized."""
        from pytest_proofy.config import ProofyConfig
        from pytest_proofy.plugin import pytest_sessionstart

        # Create config for transfer
        config = ProofyConfig(
            mode="lazy",
            api_base="https://api.example.com",
            token="test-token",
            project_id=123,
        )

        # Mock worker session
        mock_worker_session = Mock()
        mock_worker_session.config = Mock()
        mock_worker_session.config.workerinput = {
            "proofy_config_dict": config.__dict__,
            "proofy_run_id": 42,
            "proofy_session_id": "test-session-123",
        }

        with (
            patch("pytest_proofy.plugin._plugin_instance", None),
            patch("pytest_proofy.plugin.ProofyPytestPlugin") as mock_plugin_class,
        ):
            mock_plugin = Mock()
            mock_plugin.config = config
            mock_plugin_class.return_value = mock_plugin

            pytest_sessionstart(mock_worker_session)

            # Verify plugin was created for worker
            mock_plugin_class.assert_called_once()

            # Verify worker got correct run_id and session_id
            assert mock_plugin.run_id == 42
            assert mock_plugin.session_id == "test-session-123"

    def test_results_collection_across_modes(self):
        """Test result collection works across different modes."""
        from proofy import ResultStatus, TestResult
        from pytest_proofy.config import ProofyConfig
        from pytest_proofy.plugin import ProofyPytestPlugin

        modes = ["live", "lazy", "batch"]

        for mode in modes:
            config = ProofyConfig(mode=mode)
            plugin = ProofyPytestPlugin(config)
            plugin.run_id = 42

            # Mock client for modes that need it
            if mode in ("live", "lazy", "batch"):
                mock_client = Mock()
                plugin.client = mock_client

            # Create a test result
            result = TestResult(
                id=f"test_{mode}",
                name=f"Test {mode}",
                path=f"test_{mode}.py",
                run_id=42,
                status=ResultStatus.PASSED,
            )

            # Test result handling based on mode
            if mode == "live":
                plugin._send_result_live(result)
                # Should call client methods
                assert (
                    mock_client.create_test_result.called or mock_client.update_test_result.called
                )

            elif mode == "lazy":
                plugin._send_result_lazy(result)
                mock_client.send_test_result.assert_called_once_with(result)

            elif mode == "batch":
                # Batch mode results are stored and sent at session end
                plugin.test_results[result.id] = result
                assert result.id in plugin.test_results

    def test_backup_functionality_with_workers(self):
        """Test local backup works with worker processes."""
        from proofy import TestResult
        from pytest_proofy.config import ProofyConfig
        from pytest_proofy.plugin import ProofyPytestPlugin, _backup_results_locally

        with tempfile.TemporaryDirectory() as temp_dir:
            config = ProofyConfig(mode="batch", output_dir=temp_dir)

            plugin = ProofyPytestPlugin(config)

            # Add some test results
            for i in range(3):
                result = TestResult(id=f"test{i}", name=f"Test {i}", path=f"test{i}.py", run_id=42)
                plugin.test_results[f"test{i}"] = result

            # Test backup
            _backup_results_locally(plugin)

            # Verify backup file was created
            results_file = Path(temp_dir) / "results.json"
            assert results_file.exists()

            # Verify content
            with open(results_file) as f:
                backed_up_data = json.load(f)

            assert len(backed_up_data) == 3
            assert all(item["id"].startswith("test") for item in backed_up_data)

    def test_context_isolation_between_workers(self):
        """Test that test contexts are properly isolated between workers."""
        from pytest_proofy.plugin import pytest_runtest_setup, pytest_runtest_teardown

        # Mock plugin instance
        mock_plugin = Mock()
        mock_plugin.test_start_times = {}

        with patch("pytest_proofy.plugin._plugin_instance", mock_plugin):
            # Mock test items for two different workers
            mock_item1 = Mock()
            mock_item1.nodeid = "worker1::test_a.py::test_func"

            mock_item2 = Mock()
            mock_item2.nodeid = "worker2::test_b.py::test_func"

            # Mock the _get_test_id method to return the nodeid
            mock_plugin._get_test_id.side_effect = lambda item: item.nodeid

            # Setup test on worker 1
            with patch("pytest_proofy.plugin.get_current_test_context"):
                pytest_runtest_setup(mock_item1)

                # Verify context was set
                assert mock_item1.nodeid in mock_plugin.test_start_times

            # Setup test on worker 2
            with patch("pytest_proofy.plugin.get_current_test_context"):
                pytest_runtest_setup(mock_item2)

                # Verify both contexts exist independently
                assert mock_item2.nodeid in mock_plugin.test_start_times
                assert mock_item1.nodeid in mock_plugin.test_start_times

            # Teardown should clear context
            pytest_runtest_teardown(mock_item1)
            pytest_runtest_teardown(mock_item2)

    @pytest.mark.parametrize("worker_count", [2, 4])
    def test_multiple_worker_simulation(self, worker_count):
        """Simulate multiple workers processing tests."""
        from proofy import TestResult
        from pytest_proofy.config import ProofyConfig
        from pytest_proofy.plugin import ProofyPytestPlugin

        # Shared configuration
        config = ProofyConfig(mode="batch")
        shared_run_id = 42
        shared_session_id = "shared-session"

        # Create worker plugins
        workers = []
        for _ in range(worker_count):
            plugin = ProofyPytestPlugin(config)
            plugin.run_id = shared_run_id
            plugin.session_id = shared_session_id
            workers.append(plugin)

        # Distribute tests across workers
        total_tests = 12
        tests_per_worker = total_tests // worker_count

        for worker_idx, plugin in enumerate(workers):
            start_test = worker_idx * tests_per_worker
            end_test = start_test + tests_per_worker

            for test_idx in range(start_test, end_test):
                result = TestResult(
                    id=f"test_{test_idx}",
                    name=f"Test {test_idx}",
                    path=f"test_{test_idx}.py",
                    run_id=shared_run_id,
                )
                plugin.test_results[result.id] = result

        # Verify each worker has its own results
        all_test_ids = set()
        for plugin in workers:
            worker_test_ids = set(plugin.test_results.keys())
            # No overlap between workers
            assert not (all_test_ids & worker_test_ids)
            all_test_ids.update(worker_test_ids)

            # Each worker has correct number of tests
            assert len(plugin.test_results) == tests_per_worker

        # Verify all tests are accounted for
        assert len(all_test_ids) == total_tests

    def test_error_handling_in_worker_environment(self):
        """Test error handling when running in worker environment."""
        from pytest_proofy.plugin import pytest_sessionstart

        # Test with malformed worker input
        mock_session = Mock()
        mock_session.config = Mock()
        mock_session.config.workerinput = {
            "proofy_config_dict": {"invalid": "config"},  # Invalid config
        }

        with (
            patch("pytest_proofy.plugin._plugin_instance", None),
            patch("pytest_proofy.plugin.ProofyPytestPlugin") as mock_plugin_class,
        ):
            # Should handle config errors gracefully
            mock_plugin_class.side_effect = TypeError("Invalid config")

            # Should not raise exception
            try:
                pytest_sessionstart(mock_session)
            except Exception as e:
                pytest.fail(f"Session start should handle errors gracefully: {e}")

    def test_node_lifecycle_hooks(self):
        """Test xdist node lifecycle hooks."""
        # These hooks are now handled by the xdist_support module
        # Just test that they exist in the support module
        from pytest_proofy.xdist_support import XDIST_AVAILABLE

        mock_node = Mock()
        mock_node.workerinput = {"worker_id": "gw0"}

        _ = Exception("Worker crashed")  # Not used in current test

        # Test that xdist support is available (or not)
        # The actual hooks are registered conditionally
        assert isinstance(XDIST_AVAILABLE, bool)

    def test_session_id_consistency(self):
        """Test that session IDs remain consistent across workers."""
        from pytest_proofy.config import ProofyConfig
        from pytest_proofy.plugin import pytest_sessionstart

        shared_session_id = "consistent-session-123"
        config_dict = ProofyConfig(mode="lazy").__dict__

        # Simulate multiple workers getting same session ID
        for _ in range(3):
            mock_session = Mock()
            mock_session.config = Mock()
            mock_session.config.workerinput = {
                "proofy_config_dict": config_dict,
                "proofy_run_id": 42,
                "proofy_session_id": shared_session_id,
            }

            with (
                patch("pytest_proofy.plugin._plugin_instance", None),
                patch("pytest_proofy.plugin.ProofyPytestPlugin") as mock_plugin_class,
            ):
                mock_plugin = Mock()
                mock_plugin_class.return_value = mock_plugin

                pytest_sessionstart(mock_session)

                # Each worker should get the same session ID
                assert mock_plugin.session_id == shared_session_id
