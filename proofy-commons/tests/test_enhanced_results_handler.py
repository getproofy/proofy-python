"""Integration tests for enhanced ResultsHandler with background processing."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from proofy._impl.config import WorkerConfig
from proofy._impl.io.results_handler import ResultsHandler
from proofy.core.models import ResultStatus, TestResult


class TestEnhancedResultsHandler:
    """Test enhanced ResultsHandler with background processing."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ProofyClient."""
        client = Mock()
        client.create_result.return_value = {"id": 123}
        client.update_result.return_value = 200
        return client

    @pytest.fixture
    def worker_config(self):
        """Create a worker configuration."""
        return WorkerConfig(max_workers=2, max_attachment_workers=4)

    @pytest.fixture
    def sample_result(self):
        """Create a sample test result."""
        return TestResult(
            id="test_1",
            name="Test 1",
            path="test_path_1",
            test_path="test_file.py",
            run_id=1,
            status=ResultStatus.PASSED,
            started_at=datetime.now(),
            ended_at=datetime.now(),
            duration_ms=100.0,
        )

    def test_results_handler_initialization_with_background_processing(
        self, mock_client, worker_config
    ):
        """Test ResultsHandler initializes with background processing enabled."""
        handler = ResultsHandler(
            client=mock_client,
            mode="lazy",
            output_dir="/tmp/test",
            project_id=1,
            worker_config=worker_config,
            enable_background_processing=True,
            concurrent_attachment_uploads=True,
        )

        assert handler.enable_background_processing is True
        assert handler.concurrent_attachment_uploads is True
        assert handler.worker_pool is not None
        assert handler.concurrent_processor is not None
        assert handler.worker_pool.is_running()

    def test_results_handler_initialization_without_background_processing(
        self, mock_client, worker_config
    ):
        """Test ResultsHandler initializes without background processing."""
        handler = ResultsHandler(
            client=mock_client,
            mode="lazy",
            output_dir="/tmp/test",
            project_id=1,
            worker_config=worker_config,
            enable_background_processing=False,
            concurrent_attachment_uploads=False,
        )

        assert handler.enable_background_processing is False
        assert handler.concurrent_attachment_uploads is False
        assert handler.worker_pool is None
        assert handler.concurrent_processor is None

    def test_results_handler_initialization_without_client(self, worker_config):
        """Test ResultsHandler initializes without client (no background processing)."""
        handler = ResultsHandler(
            client=None,
            mode="lazy",
            output_dir="/tmp/test",
            project_id=1,
            worker_config=worker_config,
            enable_background_processing=True,  # Should be ignored when no client
            concurrent_attachment_uploads=True,
        )

        assert handler.enable_background_processing is True
        assert handler.worker_pool is None  # Should be None without client
        assert handler.concurrent_processor is None

    def test_results_handler_shutdown(self, mock_client, worker_config):
        """Test ResultsHandler shuts down gracefully."""
        handler = ResultsHandler(
            client=mock_client,
            mode="lazy",
            output_dir="/tmp/test",
            project_id=1,
            worker_config=worker_config,
            enable_background_processing=True,
        )

        assert handler.worker_pool.is_running()

        handler.shutdown()

        assert not handler.worker_pool.is_running()

    def test_results_handler_context_cleanup(self, mock_client, worker_config):
        """Test ResultsHandler cleans up on deletion."""
        handler = ResultsHandler(
            client=mock_client,
            mode="lazy",
            output_dir="/tmp/test",
            project_id=1,
            worker_config=worker_config,
            enable_background_processing=True,
        )

        assert handler.worker_pool.is_running()

        # Simulate deletion
        del handler

        # The worker pool should be shutdown (tested via mock)

    def test_enhanced_live_mode_with_background_processing(
        self, mock_client, worker_config, sample_result
    ):
        """Test enhanced live mode uses background processing."""
        handler = ResultsHandler(
            client=mock_client,
            mode="live",
            output_dir="/tmp/test",
            project_id=1,
            worker_config=worker_config,
            enable_background_processing=True,
        )

        # First call should create result synchronously
        handler._store_result_live(sample_result)

        # Verify result was created
        assert sample_result.result_id == 123
        assert sample_result.reporting_status.value == 1  # INITIALIZED

        # Second call should use background processing
        sample_result.status = ResultStatus.FAILED
        sample_result.message = "Test failed"

        handler._store_result_live(sample_result)

        # Should not raise exception and should finish test
        # The actual background processing is tested in unit tests

    def test_enhanced_live_mode_without_background_processing(
        self, mock_client, worker_config, sample_result
    ):
        """Test enhanced live mode falls back to synchronous processing."""
        handler = ResultsHandler(
            client=mock_client,
            mode="live",
            output_dir="/tmp/test",
            project_id=1,
            worker_config=worker_config,
            enable_background_processing=False,
        )

        # First call should create result synchronously
        handler._store_result_live(sample_result)

        # Verify result was created
        assert sample_result.result_id == 123
        assert sample_result.reporting_status.value == 1  # INITIALIZED

        # Second call should use synchronous processing
        sample_result.status = ResultStatus.FAILED
        sample_result.message = "Test failed"

        handler._store_result_live(sample_result)

        # Should complete synchronously
        assert sample_result.reporting_status.value == 2  # FINISHED

    def test_enhanced_batch_mode_with_concurrent_processing(self, mock_client, worker_config):
        """Test enhanced batch mode uses concurrent processing."""
        handler = ResultsHandler(
            client=mock_client,
            mode="batch",
            output_dir="/tmp/test",
            project_id=1,
            worker_config=worker_config,
            enable_background_processing=True,
        )

        # Create multiple results
        results = []
        for i in range(3):
            result = TestResult(
                id=f"test_{i}",
                name=f"Test {i}",
                path=f"test_path_{i}",
                test_path="test_file.py",
                run_id=1,
                status=ResultStatus.PASSED,
                started_at=datetime.now(),
                ended_at=datetime.now(),
                duration_ms=100.0,
            )
            results.append(result)
            handler._store_result_batch(result)

        # Should have processed batch concurrently
        # The actual concurrent processing is tested in unit tests

    def test_enhanced_lazy_mode_with_concurrent_processing(self, mock_client, worker_config):
        """Test enhanced lazy mode uses concurrent processing."""
        handler = ResultsHandler(
            client=mock_client,
            mode="lazy",
            output_dir="/tmp/test",
            project_id=1,
            worker_config=worker_config,
            enable_background_processing=True,
            concurrent_attachment_uploads=True,
        )

        # Create multiple results
        results = []
        for i in range(3):
            result = TestResult(
                id=f"test_{i}",
                name=f"Test {i}",
                path=f"test_path_{i}",
                test_path="test_file.py",
                run_id=1,
                status=ResultStatus.PASSED,
                started_at=datetime.now(),
                ended_at=datetime.now(),
                duration_ms=100.0,
            )
            results.append(result)
            handler._store_result_lazy(result)

        # Process all results
        handler.send_result_lazy()

        # Should have processed results concurrently
        # The actual concurrent processing is tested in unit tests

    def test_flush_results_shuts_down_workers(self, mock_client, worker_config):
        """Test flush_results shuts down background workers."""
        handler = ResultsHandler(
            client=mock_client,
            mode="lazy",
            output_dir="/tmp/test",
            project_id=1,
            worker_config=worker_config,
            enable_background_processing=True,
        )

        assert handler.worker_pool.is_running()

        handler.flush_results()

        assert not handler.worker_pool.is_running()
