"""Tests for background worker functionality."""

import pytest
from proofy._impl.config import WorkerConfig
from proofy._impl.io.background_workers import BackgroundWorkerPool


class TestBackgroundWorkerPool:
    """Test BackgroundWorkerPool functionality."""

    def test_worker_pool_initialization(self):
        """Test worker pool initializes correctly."""
        config = WorkerConfig(max_workers=2, max_attachment_workers=4)
        pool = BackgroundWorkerPool(config)

        assert pool.config == config
        assert not pool.is_running()
        assert pool._result_executor is None
        assert pool._attachment_executor is None

    def test_worker_pool_start(self):
        """Test worker pool starts correctly."""
        config = WorkerConfig(max_workers=2, max_attachment_workers=4)
        pool = BackgroundWorkerPool(config)

        pool.start()

        assert pool.is_running()
        assert pool._result_executor is not None
        assert pool._attachment_executor is not None

    def test_worker_pool_submit_tasks(self):
        """Test task submission works correctly."""
        config = WorkerConfig(max_workers=2, max_attachment_workers=4)
        pool = BackgroundWorkerPool(config)
        pool.start()

        # Test result task submission
        def test_func(x):
            return x * 2

        future = pool.submit_result_task(test_func, 5)
        result = future.result(timeout=5.0)
        assert result == 10

        # Test attachment task submission
        future = pool.submit_attachment_task(test_func, 3)
        result = future.result(timeout=5.0)
        assert result == 6

    def test_worker_pool_shutdown(self):
        """Test worker pool shuts down gracefully."""
        config = WorkerConfig(max_workers=2, max_attachment_workers=4)
        pool = BackgroundWorkerPool(config)
        pool.start()

        assert pool.is_running()

        pool.shutdown()

        assert not pool.is_running()
        assert pool._result_executor is None
        assert pool._attachment_executor is None

    def test_worker_pool_context_manager(self):
        """Test worker pool works as context manager."""
        config = WorkerConfig(max_workers=2, max_attachment_workers=4)

        with BackgroundWorkerPool(config) as pool:
            assert pool.is_running()

            # Submit a task
            future = pool.submit_result_task(lambda x: x + 1, 5)
            result = future.result(timeout=5.0)
            assert result == 6

        # Pool should be shutdown after context exit
        assert not pool.is_running()

    def test_worker_pool_stats(self):
        """Test worker pool statistics."""
        config = WorkerConfig(max_workers=3, max_attachment_workers=5)
        pool = BackgroundWorkerPool(config)

        stats = pool.get_stats()
        assert stats["shutdown"] is False
        assert stats["result_workers"] == 3
        assert stats["attachment_workers"] == 5
        assert stats["result_pool_active"] is False
        assert stats["attachment_pool_active"] is False

        pool.start()
        stats = pool.get_stats()
        assert stats["shutdown"] is False
        assert stats["result_pool_active"] is True
        assert stats["attachment_pool_active"] is True

    def test_worker_pool_submit_after_shutdown(self):
        """Test that submitting tasks after shutdown raises error."""
        config = WorkerConfig(max_workers=2, max_attachment_workers=4)
        pool = BackgroundWorkerPool(config)
        pool.start()
        pool.shutdown()

        with pytest.raises(RuntimeError, match="Cannot submit tasks after shutdown"):
            pool.submit_result_task(lambda: None)

        with pytest.raises(RuntimeError, match="Cannot submit tasks after shutdown"):
            pool.submit_attachment_task(lambda: None)

    def test_worker_pool_start_after_shutdown(self):
        """Test that starting after shutdown raises error."""
        config = WorkerConfig(max_workers=2, max_attachment_workers=4)
        pool = BackgroundWorkerPool(config)
        pool.start()
        pool.shutdown()

        with pytest.raises(RuntimeError, match="Cannot start worker pool after shutdown"):
            pool.start()


class TestWorkerConfig:
    """Test WorkerConfig functionality."""

    def test_worker_config_defaults(self):
        """Test WorkerConfig has correct defaults."""
        config = WorkerConfig()

        assert config.max_workers == 4
        assert config.max_attachment_workers == 8
        assert config.task_timeout == 30.0
        assert config.shutdown_timeout == 30.0
        assert config.retry_attempts == 3
        assert config.retry_delay == 1.0
        assert config.max_concurrent_results == 10
        assert config.max_concurrent_attachments == 20

    def test_worker_config_custom_values(self):
        """Test WorkerConfig accepts custom values."""
        config = WorkerConfig(
            max_workers=8,
            max_attachment_workers=16,
            task_timeout=60.0,
            shutdown_timeout=45.0,
            retry_attempts=5,
            retry_delay=2.0,
            max_concurrent_results=20,
            max_concurrent_attachments=40,
        )

        assert config.max_workers == 8
        assert config.max_attachment_workers == 16
        assert config.task_timeout == 60.0
        assert config.shutdown_timeout == 45.0
        assert config.retry_attempts == 5
        assert config.retry_delay == 2.0
        assert config.max_concurrent_results == 20
        assert config.max_concurrent_attachments == 40
