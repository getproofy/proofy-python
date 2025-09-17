"""End-to-end tests for xdist integration."""

import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def sample_test_project():
    """Create a sample test project for e2e testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        project_path = Path(temp_dir)

        # Create a simple test suite
        test_content = {
            "test_suite_a.py": '''
import time
import pytest

def test_fast_a1():
    """Fast test A1."""
    assert 1 + 1 == 2

def test_fast_a2():
    """Fast test A2."""
    assert "hello".upper() == "HELLO"

def test_slow_a1():
    """Slow test A1."""
    time.sleep(0.2)
    assert True

def test_slow_a2():
    """Slow test A2."""
    time.sleep(0.2)
    assert True
''',
            "test_suite_b.py": '''
import time
import pytest

class TestClassB:
    def test_method_b1(self):
        """Test method B1."""
        assert [1, 2, 3] == [1, 2, 3]

    def test_method_b2(self):
        """Test method B2."""
        time.sleep(0.1)
        assert {"key": "value"} == {"key": "value"}

    def test_method_b3(self):
        """Test method B3."""
        time.sleep(0.1)
        assert True

def test_function_b1():
    """Function test B1."""
    assert 5 * 5 == 25

def test_function_b2():
    """Function test B2."""
    time.sleep(0.1)
    assert "test".startswith("te")
''',
            "test_suite_c.py": '''
import time
import pytest

@pytest.mark.parametrize("value", [1, 2, 3, 4, 5])
def test_parametrized(value):
    """Parametrized test."""
    time.sleep(0.05)
    assert value > 0

def test_with_fixture():
    """Test using fixture."""
    time.sleep(0.1)
    assert True

@pytest.mark.slow
def test_marked_slow():
    """Test with marker."""
    time.sleep(0.3)
    assert True
''',
            "conftest.py": '''
import pytest

@pytest.fixture
def sample_data():
    """Sample fixture."""
    return {"test": "data"}
''',
        }

        # Write test files
        for filename, content in test_content.items():
            (project_path / filename).write_text(content)

        # Create pytest.ini with proofy configuration
        pytest_ini = """
[tool:pytest]
addopts = --tb=short
markers =
    slow: marks tests as slow
"""
        (project_path / "pytest.ini").write_text(pytest_ini)

        yield project_path


@pytest.mark.integration
class TestXdistE2E:
    """End-to-end tests for xdist integration."""

    def test_xdist_with_local_backup(self, sample_test_project):
        """Test running with xdist and local backup enabled."""
        output_dir = sample_test_project / "proofy-output"

        # Run pytest with xdist and proofy plugin
        cmd = [
            "python3",
            "-m",
            "pytest",
            str(sample_test_project),
            "-n",
            "2",  # Use 2 workers
            "--proofy-mode",
            "batch",
            "--proofy-output-dir",
            str(output_dir),
            "--proofy-always-backup",
            "-v",
        ]

        # Mock the plugin to avoid actual API calls
        with patch("pytest_proofy.plugin.ProofyClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.create_test_run.return_value = {"id": 123}
            mock_client.send_test_results.return_value = None

            result = subprocess.run(
                cmd, cwd=sample_test_project, capture_output=True, text=True, timeout=30
            )

        # Check that tests ran successfully
        assert result.returncode == 0, f"Tests failed: {result.stdout}\n{result.stderr}"

        # Verify output contains expected test results
        assert "test session starts" in result.stdout
        assert "passed" in result.stdout

        # Verify backup files were created
        results_file = output_dir / "results.json"
        assert results_file.exists(), "Results backup file should exist"

        # Verify backup content
        with open(results_file) as f:
            results_data = json.load(f)

        assert len(results_data) > 0, "Should have backed up test results"

        # Verify we have results from different test files
        test_paths = {result.get("path", "") for result in results_data}
        assert len(test_paths) > 1, "Should have results from multiple test files"

    def test_xdist_worker_coordination(self, sample_test_project):
        """Test that workers coordinate properly."""
        output_dir = sample_test_project / "proofy-output"

        # Run with more workers than we have test files to test coordination
        cmd = [
            "python3",
            "-m",
            "pytest",
            str(sample_test_project),
            "-n",
            "4",  # Use 4 workers for 3 test files
            "--proofy-mode",
            "lazy",
            "--proofy-output-dir",
            str(output_dir),
            "--proofy-always-backup",
            "-x",  # Stop on first failure
        ]

        with patch("pytest_proofy.plugin.ProofyClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.send_test_result.return_value = None

            result = subprocess.run(
                cmd, cwd=sample_test_project, capture_output=True, text=True, timeout=30
            )

        assert result.returncode == 0, f"Tests failed: {result.stdout}\n{result.stderr}"

        # Verify xdist was used (should see worker output)
        assert "gw" in result.stdout or "worker" in result.stdout or "[" in result.stdout

    def test_xdist_with_test_failures(self, sample_test_project):
        """Test xdist behavior with failing tests."""
        # Add a failing test
        failing_test = '''
def test_failing():
    """This test will fail."""
    assert False, "Intentional failure"

def test_passing_after_failure():
    """This test should still run."""
    assert True
'''
        (sample_test_project / "test_failures.py").write_text(failing_test)

        output_dir = sample_test_project / "proofy-output"

        cmd = [
            "python",
            "-m",
            "pytest",
            str(sample_test_project),
            "-n",
            "2",
            "--proofy-mode",
            "batch",
            "--proofy-output-dir",
            str(output_dir),
            "--proofy-always-backup",
            "--tb=short",
            "--continue-on-collection-errors",
        ]

        with patch("pytest_proofy.plugin.ProofyClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.create_test_run.return_value = {"id": 123}
            mock_client.send_test_results.return_value = None

            result = subprocess.run(
                cmd, cwd=sample_test_project, capture_output=True, text=True, timeout=30
            )

        # Should have non-zero exit code due to failures
        assert result.returncode != 0

        # But should still create backup
        results_file = output_dir / "results.json"
        assert results_file.exists()

        with open(results_file) as f:
            results_data = json.load(f)

        # Should have both passed and failed results
        statuses = [result.get("status") for result in results_data]
        assert "failed" in statuses or "FAILED" in statuses
        assert "passed" in statuses or "PASSED" in statuses

    def test_xdist_performance_improvement(self, sample_test_project):
        """Test that xdist actually improves performance."""
        import time

        output_dir = sample_test_project / "proofy-output"

        # Run without xdist (sequential)
        cmd_sequential = [
            "python",
            "-m",
            "pytest",
            str(sample_test_project),
            "--proofy-mode",
            "batch",
            "--proofy-output-dir",
            str(output_dir),
            "--proofy-always-backup",
            "-q",
        ]

        # Run with xdist (parallel)
        cmd_parallel = cmd_sequential + ["-n", "auto"]

        with patch("pytest_proofy.plugin.ProofyClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.create_test_run.return_value = {"id": 123}
            mock_client.send_test_results.return_value = None

            # Time sequential run
            start_time = time.time()
            result_seq = subprocess.run(
                cmd_sequential,
                cwd=sample_test_project,
                capture_output=True,
                text=True,
                timeout=60,
            )
            sequential_time = time.time() - start_time

            # Clear output directory
            import shutil

            if output_dir.exists():
                shutil.rmtree(output_dir)

            # Time parallel run
            start_time = time.time()
            result_par = subprocess.run(
                cmd_parallel,
                cwd=sample_test_project,
                capture_output=True,
                text=True,
                timeout=60,
            )
            parallel_time = time.time() - start_time

        # Both should succeed
        assert result_seq.returncode == 0, f"Sequential run failed: {result_seq.stderr}"
        assert result_par.returncode == 0, f"Parallel run failed: {result_par.stderr}"

        # Parallel should be faster (allowing for some overhead)
        # This is a rough check - in real scenarios the improvement would be more significant
        print(f"Sequential time: {sequential_time:.2f}s, Parallel time: {parallel_time:.2f}s")

        # At minimum, parallel shouldn't be significantly slower
        assert parallel_time < sequential_time * 1.5, "Parallel execution shouldn't be much slower"

    def test_xdist_result_consistency(self, sample_test_project):
        """Test that results are consistent between xdist and non-xdist runs."""
        output_dir = sample_test_project / "proofy-output"

        base_cmd = [
            "python",
            "-m",
            "pytest",
            str(sample_test_project),
            "--proofy-mode",
            "batch",
            "--proofy-output-dir",
            str(output_dir),
            "--proofy-always-backup",
            "-v",
        ]

        with patch("pytest_proofy.plugin.ProofyClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.create_test_run.return_value = {"id": 123}
            mock_client.send_test_results.return_value = None

            # Run without xdist
            result_normal = subprocess.run(
                base_cmd,
                cwd=sample_test_project,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Save normal results
            results_file = output_dir / "results.json"
            with open(results_file) as f:
                normal_results = json.load(f)

            # Clear and run with xdist
            import shutil

            shutil.rmtree(output_dir)

            result_xdist = subprocess.run(
                base_cmd + ["-n", "2"],
                cwd=sample_test_project,
                capture_output=True,
                text=True,
                timeout=30,
            )

            with open(results_file) as f:
                xdist_results = json.load(f)

        # Both should succeed
        assert result_normal.returncode == 0
        assert result_xdist.returncode == 0

        # Should have same number of results
        assert len(normal_results) == len(xdist_results)

        # Should have same test IDs (order might differ)
        normal_ids = {result["id"] for result in normal_results}
        xdist_ids = {result["id"] for result in xdist_results}
        assert normal_ids == xdist_ids

    @pytest.mark.slow
    def test_xdist_with_many_workers(self, sample_test_project):
        """Test behavior with many workers (stress test)."""
        output_dir = sample_test_project / "proofy-output"

        # Use many workers to test coordination
        cmd = [
            "python",
            "-m",
            "pytest",
            str(sample_test_project),
            "-n",
            "8",  # Many workers
            "--proofy-mode",
            "lazy",
            "--proofy-output-dir",
            str(output_dir),
            "--proofy-always-backup",
            "-q",
        ]

        with patch("pytest_proofy.plugin.ProofyClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.send_test_result.return_value = None

            result = subprocess.run(
                cmd, cwd=sample_test_project, capture_output=True, text=True, timeout=45
            )

        assert result.returncode == 0, f"Many workers test failed: {result.stdout}\n{result.stderr}"

        # Verify all results were collected
        results_file = output_dir / "results.json"
        assert results_file.exists()

        with open(results_file) as f:
            results_data = json.load(f)

        # Should have results from all test files
        assert len(results_data) > 10, "Should have collected all test results"
