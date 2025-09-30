"""Tests for concurrent processing functionality."""

from datetime import datetime
from unittest.mock import Mock

import pytest
from proofy._impl.config import WorkerConfig
from proofy._impl.io.background_workers import BackgroundWorkerPool
from proofy._impl.io.concurrent_processor import (
    ConcurrentResultProcessor,
    ProcessingResult,
)
from proofy.core.models import Attachment, ResultStatus, TestResult


class TestConcurrentResultProcessor:
    """Test ConcurrentResultProcessor functionality."""

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
    def worker_pool(self, worker_config):
        """Create a worker pool."""
        return BackgroundWorkerPool(worker_config)

    @pytest.fixture
    def processor(self, worker_pool, mock_client, worker_config):
        """Create a concurrent processor."""
        return ConcurrentResultProcessor(worker_pool, mock_client, worker_config)

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

    def test_processor_initialization(self, processor, worker_pool, mock_client, worker_config):
        """Test processor initializes correctly."""
        assert processor.worker_pool == worker_pool
        assert processor.client == mock_client
        assert processor.config == worker_config

    def test_process_results_concurrently_empty_list(self, processor):
        """Test processing empty results list."""
        result = processor.process_results_concurrently([])

        assert isinstance(result, ProcessingResult)
        assert result.total == 0
        assert result.success_count == 0
        assert result.failure_count == 0
        assert result.success_rate == 0.0

    def test_process_results_concurrently_single_result(
        self, processor, sample_result, mock_client
    ):
        """Test processing single result."""
        processor.worker_pool.start()

        result = processor.process_results_concurrently([sample_result])

        assert isinstance(result, ProcessingResult)
        assert result.total == 1
        assert result.success_count == 1
        assert result.failure_count == 0
        assert result.success_rate == 1.0

        # Verify client was called
        mock_client.create_result.assert_called_once()

    def test_process_results_concurrently_multiple_results(self, processor, mock_client):
        """Test processing multiple results."""
        processor.worker_pool.start()

        results = [
            TestResult(
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
            for i in range(3)
        ]

        result = processor.process_results_concurrently(results)

        assert isinstance(result, ProcessingResult)
        assert result.total == 3
        assert result.success_count == 3
        assert result.failure_count == 0
        assert result.success_rate == 1.0

        # Verify client was called for each result
        assert mock_client.create_result.call_count == 3

    def test_process_results_concurrently_with_failure(self, processor, mock_client):
        """Test processing results with some failures."""
        processor.worker_pool.start()

        # Make one call fail
        mock_client.create_result.side_effect = [
            {"id": 123},  # Success
            Exception("API Error"),  # Failure
            {"id": 125},  # Success
        ]

        results = [
            TestResult(
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
            for i in range(3)
        ]

        result = processor.process_results_concurrently(results)

        assert isinstance(result, ProcessingResult)
        assert result.total == 3
        assert result.success_count == 2
        assert result.failure_count == 1
        assert result.success_rate == 2 / 3

    def test_upload_attachments_concurrently_no_attachments(self, processor, sample_result):
        """Test uploading attachments when result has no attachments."""
        processor.worker_pool.start()

        futures = processor.upload_attachments_concurrently(sample_result)

        assert futures == []

    def test_upload_attachments_concurrently_with_attachments(self, processor, sample_result):
        """Test uploading attachments when result has attachments."""
        processor.worker_pool.start()

        # Add attachments to the result
        sample_result.attachments = [
            Attachment(name="file1.txt", path="/tmp/file1.txt", mime_type="text/plain"),
            Attachment(name="file2.txt", path="/tmp/file2.txt", mime_type="text/plain"),
        ]
        sample_result.result_id = 123  # Required for uploads

        futures = processor.upload_attachments_concurrently(sample_result)

        assert len(futures) == 2
        assert all(hasattr(future, "result") for future in futures)

    def test_wait_for_attachments_empty_list(self, processor):
        """Test waiting for empty attachment futures list."""
        result = processor.wait_for_attachments([])

        assert result["completed"] == 0
        assert result["failed"] == 0
        assert result["total"] == 0

    def test_wait_for_attachments_success(self, processor):
        """Test waiting for successful attachment uploads."""
        processor.worker_pool.start()

        # Create some successful futures
        futures = [
            processor.worker_pool.submit_attachment_task(lambda: "success"),
            processor.worker_pool.submit_attachment_task(lambda: "success"),
        ]

        result = processor.wait_for_attachments(futures)

        assert result["completed"] == 2
        assert result["failed"] == 0
        assert result["total"] == 2

    def test_wait_for_attachments_with_failures(self, processor):
        """Test waiting for attachment uploads with some failures."""
        processor.worker_pool.start()

        # Create mixed success/failure futures
        futures = [
            processor.worker_pool.submit_attachment_task(lambda: "success"),
            processor.worker_pool.submit_attachment_task(
                lambda: (_ for _ in ()).throw(Exception("Upload failed"))
            ),
            processor.worker_pool.submit_attachment_task(lambda: "success"),
        ]

        result = processor.wait_for_attachments(futures)

        assert result["completed"] == 2
        assert result["failed"] == 1
        assert result["total"] == 3


class TestProcessingResult:
    """Test ProcessingResult functionality."""

    def test_processing_result_properties(self):
        """Test ProcessingResult properties."""
        completed = [("result1", "data1"), ("result2", "data2")]
        failed = [("result3", Exception("Error"))]
        total = 3

        result = ProcessingResult(completed=completed, failed=failed, total=total)

        assert result.success_count == 2
        assert result.failure_count == 1
        assert result.success_rate == 2 / 3
        assert result.total == 3

    def test_processing_result_zero_total(self):
        """Test ProcessingResult with zero total."""
        result = ProcessingResult(completed=[], failed=[], total=0)

        assert result.success_count == 0
        assert result.failure_count == 0
        assert result.success_rate == 0.0
        assert result.total == 0
