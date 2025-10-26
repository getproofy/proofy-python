"""Tests for ResultsHandler components (Phase 3)."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from proofy._internal.config import ProofyConfig
from proofy._internal.context import ContextService
from proofy._internal.results import (
    BatchPublisher,
    LazyPublisher,
    LivePublisher,
    ResultBuffer,
    RunManager,
)
from proofy.core.client import Client
from proofy.core.models import ReportingStatus, ResultStatus, RunStatus, TestResult


class TestResultBuffer:
    """Test ResultBuffer component."""

    def test_buffer_initialization(self) -> None:
        """Test buffer initializes with correct batch size."""
        buffer = ResultBuffer(batch_size=50)
        assert buffer.batch_size == 50
        assert len(buffer) == 0

    def test_add_result(self) -> None:
        """Test adding results to buffer."""
        buffer = ResultBuffer(batch_size=10)
        buffer.add_result("test-1")
        buffer.add_result("test-2")

        assert len(buffer) == 2
        assert buffer.get_pending() == ["test-1", "test-2"]

    def test_should_flush(self) -> None:
        """Test should_flush returns True when threshold reached."""
        buffer = ResultBuffer(batch_size=3)
        buffer.add_result("test-1")
        buffer.add_result("test-2")

        assert not buffer.should_flush()

        buffer.add_result("test-3")
        assert buffer.should_flush()

    def test_clear(self) -> None:
        """Test clearing the buffer."""
        buffer = ResultBuffer(batch_size=10)
        buffer.add_result("test-1")
        buffer.add_result("test-2")

        buffer.clear()
        assert len(buffer) == 0
        assert buffer.get_pending() == []

    def test_get_pending_returns_copy(self) -> None:
        """Test get_pending returns a copy, not reference."""
        buffer = ResultBuffer(batch_size=10)
        buffer.add_result("test-1")

        pending = buffer.get_pending()
        pending.append("test-2")

        # Original buffer should not be affected
        assert len(buffer) == 1


class TestRunManager:
    """Test RunManager component."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock client."""
        return Mock(spec=Client)

    @pytest.fixture
    def context_service(self) -> ContextService:
        """Create context service."""
        service = ContextService()
        config = ProofyConfig(mode="live")
        service.start_session(config=config, run_name="Test Run")
        return service

    def test_start_new_run(self, mock_client: Mock, context_service: ContextService) -> None:
        """Test starting a new run."""
        mock_client.create_run.return_value = {"id": 123}

        manager = RunManager(client=mock_client, context=context_service)
        run_id = manager.start_run(
            project_id=1,
            name="Test Run",
            attributes={"key": "value"},
        )

        assert run_id == 123
        assert manager.get_run_id() == 123
        assert context_service.session_ctx.run_id == 123
        mock_client.create_run.assert_called_once()

    def test_start_existing_run(self, mock_client: Mock, context_service: ContextService) -> None:
        """Test updating an existing run."""
        # Set existing run_id in session
        context_service.session_ctx.run_id = 456

        manager = RunManager(client=mock_client, context=context_service)
        run_id = manager.start_run(
            project_id=1,
            name="Test Run",
            attributes={"key": "value"},
        )

        assert run_id == 456
        assert manager.get_run_id() == 456
        mock_client.update_run.assert_called_once()
        mock_client.create_run.assert_not_called()

    def test_finish_run(self, mock_client: Mock, context_service: ContextService) -> None:
        """Test finishing a run."""
        manager = RunManager(client=mock_client, context=context_service)
        manager.run_id = 123
        context_service.session_ctx.run_id = 123

        manager.finish_run(status=RunStatus.FINISHED)

        mock_client.update_run.assert_called_once()
        call_args = mock_client.update_run.call_args
        assert call_args.kwargs["run_id"] == 123
        assert call_args.kwargs["status"] == RunStatus.FINISHED

    def test_finish_run_with_error_message(
        self, mock_client: Mock, context_service: ContextService
    ) -> None:
        """Test finishing a run with error message."""
        manager = RunManager(client=mock_client, context=context_service)
        manager.run_id = 123
        context_service.session_ctx.run_id = 123

        manager.finish_run(
            status=RunStatus.ABORTED,
            error_message="Test error",
        )

        # Error message should be added to run attributes
        run_attrs = context_service.get_run_attributes()
        # Check for error message with proofy prefix
        assert any("error_message" in key for key in run_attrs)


class TestPublishers:
    """Test publisher implementations."""

    @pytest.fixture
    def mock_client(self) -> Mock:
        """Create mock client."""
        client = Mock(spec=Client)
        client.create_result.return_value = {"id": 1}
        return client

    @pytest.fixture
    def context_service(self) -> ContextService:
        """Create context service with test result."""
        service = ContextService()
        config = ProofyConfig(mode="live")
        service.start_session(config=config, run_name="Test Run")
        return service

    @pytest.fixture
    def test_result(self) -> TestResult:
        """Create a test result."""
        return TestResult(
            id="test-1",
            name="test_example",
            path="tests/test_example.py",
            test_path="tests/test_example.py",
            status=ResultStatus.PASSED,
            test_identifier="tests/test_example.py::test_example",
            run_id=123,
        )

    def test_live_publisher_create_result(
        self,
        mock_client: Mock,
        context_service: ContextService,
        test_result: TestResult,
    ) -> None:
        """Test LivePublisher creates result on first publish."""
        publisher = LivePublisher(client=mock_client, context=context_service)

        publisher.publish(test_result)

        mock_client.create_result.assert_called_once()
        assert test_result.result_id == 1
        assert test_result.reporting_status == ReportingStatus.INITIALIZED

    def test_live_publisher_update_result(
        self,
        mock_client: Mock,
        context_service: ContextService,
        test_result: TestResult,
    ) -> None:
        """Test LivePublisher updates result on second publish."""
        test_result.result_id = 1
        test_result.reporting_status = ReportingStatus.INITIALIZED

        publisher = LivePublisher(client=mock_client, context=context_service)
        publisher.publish(test_result)

        mock_client.update_result.assert_called_once()
        assert test_result.reporting_status == ReportingStatus.FINISHED

    def test_lazy_publisher_defers_sending(
        self,
        mock_client: Mock,
        context_service: ContextService,
        test_result: TestResult,
    ) -> None:
        """Test LazyPublisher doesn't send immediately."""
        publisher = LazyPublisher(client=mock_client, context=context_service)

        publisher.publish(test_result)

        # Should not send immediately
        mock_client.create_result.assert_not_called()

    def test_lazy_publisher_flush(
        self,
        mock_client: Mock,
        context_service: ContextService,
        test_result: TestResult,
    ) -> None:
        """Test LazyPublisher sends results on flush."""
        # Add result to context
        context_service.start_test(test_result)
        context_service.finish_test(test_result)

        publisher = LazyPublisher(client=mock_client, context=context_service)
        publisher.flush()

        mock_client.create_result.assert_called_once()
        assert test_result.reporting_status == ReportingStatus.FINISHED

    def test_batch_publisher_buffers_results(
        self,
        mock_client: Mock,
        context_service: ContextService,
        test_result: TestResult,
    ) -> None:
        """Test BatchPublisher buffers results."""
        buffer = ResultBuffer(batch_size=5)
        publisher = BatchPublisher(
            client=mock_client,
            context=context_service,
            buffer=buffer,
        )

        context_service.start_test(test_result)
        publisher.publish(test_result)

        # Should buffer, not send immediately
        assert len(buffer) == 1
        mock_client.create_result.assert_not_called()

    def test_batch_publisher_auto_flush(
        self,
        mock_client: Mock,
        context_service: ContextService,
    ) -> None:
        """Test BatchPublisher auto-flushes when threshold reached."""
        buffer = ResultBuffer(batch_size=2)
        publisher = BatchPublisher(
            client=mock_client,
            context=context_service,
            buffer=buffer,
        )

        # Add results to context and publish
        for i in range(2):
            result = TestResult(
                id=f"test-{i}",
                name=f"test_{i}",
                path="tests/test.py",
                test_path="tests/test.py",
                status=ResultStatus.PASSED,
                test_identifier=f"test_{i}",
                run_id=123,
            )
            context_service.start_test(result)
            context_service.finish_test(result)
            publisher.publish(result)

        # Should have auto-flushed
        assert len(buffer) == 0
        assert mock_client.create_result.call_count == 2

    def test_batch_publisher_manual_flush(
        self,
        mock_client: Mock,
        context_service: ContextService,
        test_result: TestResult,
    ) -> None:
        """Test BatchPublisher manual flush."""
        buffer = ResultBuffer(batch_size=10)
        publisher = BatchPublisher(
            client=mock_client,
            context=context_service,
            buffer=buffer,
        )

        context_service.start_test(test_result)
        context_service.finish_test(test_result)
        publisher.publish(test_result)

        # Manually flush
        publisher.flush()

        assert len(buffer) == 0
        mock_client.create_result.assert_called_once()
