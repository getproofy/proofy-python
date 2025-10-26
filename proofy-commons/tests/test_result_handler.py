"""Comprehensive unit tests for ResultsHandler."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from proofy._internal.artifacts import ArtifactUploader
from proofy._internal.config import ProofyConfig
from proofy._internal.results import (
    BatchPublisher,
    LazyPublisher,
    LivePublisher,
    ResultsHandler,
    RunManager,
)
from proofy._internal.uploader import UploaderWorker
from proofy.core.client import Client
from proofy.core.models import (
    Attachment,
    ResultStatus,
    RunStatus,
    TestResult,
)


class TestResultsHandlerInit:
    """Test ResultsHandler initialization."""

    def test_init_with_complete_config(self, tmp_path: Path) -> None:
        """Test initialization with complete configuration."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="live",
        )

        handler = ResultsHandler(
            config=config,
            framework="pytest",
            disable_output=False,
        )

        assert handler.config == config
        assert handler.framework == "pytest"
        assert handler.disable_output is False
        assert handler.client is not None
        assert handler.queue is not None
        assert handler.worker is not None
        assert handler.run_manager is not None
        assert handler.publisher is not None
        assert isinstance(handler.publisher, LivePublisher)
        assert handler.attachment_service is not None
        assert handler.artifacts is not None

    def test_init_with_batch_mode(self, tmp_path: Path) -> None:
        """Test initialization with batch mode creates BatchPublisher."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="batch",
            batch_size=50,
        )

        handler = ResultsHandler(
            config=config,
            framework="pytest",
        )

        assert isinstance(handler.publisher, BatchPublisher)
        assert handler.buffer is not None
        assert handler.buffer.batch_size == 50

    def test_init_with_lazy_mode(self, tmp_path: Path) -> None:
        """Test initialization with lazy mode creates LazyPublisher."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="lazy",
        )

        handler = ResultsHandler(
            config=config,
            framework="pytest",
        )

        assert isinstance(handler.publisher, LazyPublisher)
        assert handler.buffer is None

    def test_init_with_disable_output(self, tmp_path: Path) -> None:
        """Test initialization with disable_output=True."""
        config = ProofyConfig(
            output_dir=str(tmp_path / "artifacts"),
            mode="live",
        )

        handler = ResultsHandler(
            config=config,
            framework="pytest",
            disable_output=True,
        )

        assert handler.client is None
        assert handler.queue is None
        assert handler.worker is None
        assert handler.run_manager is None
        assert handler.publisher is None
        assert handler.artifacts is None

    def test_init_missing_api_base(self, tmp_path: Path) -> None:
        """Test initialization fails with missing api_base."""
        config = ProofyConfig(
            api_base="",  # Empty string to override default
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
        )

        with pytest.raises(RuntimeError, match="Missing Proofy required configuration.*api_base"):
            ResultsHandler(
                config=config,
                framework="pytest",
                disable_output=False,
            )

    def test_init_missing_token(self, tmp_path: Path) -> None:
        """Test initialization fails with missing token."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
        )

        with pytest.raises(RuntimeError, match="Missing Proofy required configuration.*token"):
            ResultsHandler(
                config=config,
                framework="pytest",
                disable_output=False,
            )

    def test_init_missing_project_id(self, tmp_path: Path) -> None:
        """Test initialization fails with missing project_id."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            output_dir=str(tmp_path / "artifacts"),
        )

        with pytest.raises(RuntimeError, match="Missing Proofy required configuration.*project_id"):
            ResultsHandler(
                config=config,
                framework="pytest",
                disable_output=False,
            )

    def test_init_starts_worker(self, tmp_path: Path) -> None:
        """Test initialization starts uploader worker."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
        )

        with patch.object(UploaderWorker, "start") as mock_start:
            handler = ResultsHandler(
                config=config,
                framework="pytest",
            )

            mock_start.assert_called_once()
            assert handler.worker is not None


class TestResultsHandlerSessionLifecycle:
    """Test ResultsHandler session lifecycle methods."""

    @pytest.fixture
    def handler(self, tmp_path: Path) -> ResultsHandler:
        """Create a ResultsHandler with mocked dependencies."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="live",
        )

        with patch.object(UploaderWorker, "start"):
            handler = ResultsHandler(
                config=config,
                framework="pytest",
            )
            # Mock the worker to avoid actual thread operations
            handler.worker = Mock(spec=UploaderWorker)

        return handler

    def test_start_session_default_run_name(self, handler: ResultsHandler) -> None:
        """Test start_session creates default run name."""
        handler.start_session()

        session = handler.context.session_ctx
        assert session is not None
        assert session.run_name is not None
        assert "pytest" in session.run_name
        assert session.run_attributes is not None
        assert "__proofy_framework" in session.run_attributes
        assert session.run_attributes["__proofy_framework"] == "pytest"

    def test_start_session_custom_run_name(self, handler: ResultsHandler) -> None:
        """Test start_session uses custom run name from config."""
        handler.config.run_name = "My Custom Run"
        handler.start_session()

        session = handler.context.session_ctx
        assert session is not None
        assert session.run_name == "My Custom Run"

    def test_start_session_with_run_attributes(self, handler: ResultsHandler) -> None:
        """Test start_session includes user-provided run attributes."""
        handler.config.run_attributes = {"custom_key": "custom_value", "env": "staging"}
        handler.start_session()

        session = handler.context.session_ctx
        assert session is not None
        assert "custom_key" in session.run_attributes
        assert session.run_attributes["custom_key"] == "custom_value"
        assert "env" in session.run_attributes
        assert session.run_attributes["env"] == "staging"

    def test_start_session_with_existing_run_id(self, handler: ResultsHandler) -> None:
        """Test start_session with existing run ID."""
        handler.start_session(run_id=456)

        session = handler.context.session_ctx
        assert session is not None
        assert session.run_id == 456

    def test_start_session_includes_system_attributes(self, handler: ResultsHandler) -> None:
        """Test start_session includes system attributes."""
        handler.start_session()

        session = handler.context.session_ctx
        assert session is not None
        run_attrs = session.run_attributes

        # Check for expected system attributes
        assert "__proofy_framework" in run_attrs
        assert run_attrs["__proofy_framework"] == "pytest"

    def test_end_session_stops_worker(self, handler: ResultsHandler) -> None:
        """Test end_session stops uploader worker."""
        handler.start_session()
        handler.end_session()

        handler.worker.stop.assert_called_once()

    def test_end_session_logs_metrics(self, handler: ResultsHandler) -> None:
        """Test end_session logs worker metrics."""
        handler.start_session()
        handler.worker.get_metrics = Mock(return_value={"uploaded": 10, "failed": 0})

        handler.end_session()

        handler.worker.get_metrics.assert_called_once()


class TestResultsHandlerRunLifecycle:
    """Test ResultsHandler run lifecycle methods."""

    @pytest.fixture
    def handler(self, tmp_path: Path) -> ResultsHandler:
        """Create a ResultsHandler with mocked dependencies."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="live",
        )

        with patch.object(UploaderWorker, "start"):
            handler = ResultsHandler(
                config=config,
                framework="pytest",
            )
            handler.worker = Mock(spec=UploaderWorker)
            # Mock run_manager
            handler.run_manager = Mock(spec=RunManager)

        return handler

    def test_start_run_without_session(self, handler: ResultsHandler) -> None:
        """Test start_run fails without session."""
        with pytest.raises(RuntimeError, match="Session not initialized"):
            handler.start_run()

    def test_start_run_creates_new_run(self, handler: ResultsHandler) -> None:
        """Test start_run creates a new run."""
        handler.start_session()
        handler.run_manager.start_run.return_value = 123

        run_id = handler.start_run()

        assert run_id == 123
        handler.run_manager.start_run.assert_called_once()
        call_kwargs = handler.run_manager.start_run.call_args.kwargs
        assert call_kwargs["project_id"] == 1
        assert call_kwargs["name"] is not None

    def test_start_run_without_client(self, tmp_path: Path) -> None:
        """Test start_run returns None when no client configured."""
        config = ProofyConfig(
            output_dir=str(tmp_path / "artifacts"),
            mode="live",
        )

        handler = ResultsHandler(
            config=config,
            framework="pytest",
            disable_output=True,
        )

        handler.start_session()
        run_id = handler.start_run()

        assert run_id is None

    def test_start_run_without_project_id(self, tmp_path: Path) -> None:
        """Test start_run fails without project_id."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            output_dir=str(tmp_path / "artifacts"),
        )

        # Create handler with disable_output to bypass init checks
        handler = ResultsHandler(
            config=config,
            framework="pytest",
            disable_output=True,
        )

        # Manually set run_manager to simulate partial config
        handler.run_manager = Mock(spec=RunManager)
        handler.start_session()

        with pytest.raises(RuntimeError, match="project_id is required"):
            handler.start_run()

    def test_finish_run_flushes_results(self, handler: ResultsHandler) -> None:
        """Test finish_run flushes pending results."""
        handler.start_session()
        handler.run_manager.start_run.return_value = 123
        handler.start_run()

        handler.publisher = Mock()
        handler.queue = Mock()
        handler.queue.join = Mock(return_value=True)

        handler.finish_run(run_id=123, status=RunStatus.FINISHED)

        handler.publisher.flush.assert_called_once()

    def test_finish_run_waits_for_queue(self, handler: ResultsHandler) -> None:
        """Test finish_run waits for upload queue to drain."""
        handler.start_session()
        handler.run_manager.start_run.return_value = 123
        handler.start_run()

        handler.publisher = Mock()
        handler.queue = Mock()
        handler.queue.join = Mock(return_value=True)

        handler.finish_run(run_id=123, status=RunStatus.FINISHED)

        handler.queue.join.assert_called_once_with(timeout=60.0)

    def test_finish_run_with_timeout(self, handler: ResultsHandler) -> None:
        """Test finish_run logs warning if queue doesn't drain."""
        handler.start_session()
        handler.run_manager.start_run.return_value = 123
        handler.start_run()

        handler.publisher = Mock()
        handler.queue = Mock()
        handler.queue.join = Mock(return_value=False)  # Timeout

        with patch("proofy._internal.results.result_handler.logger") as mock_logger:
            handler.finish_run(run_id=123, status=RunStatus.FINISHED)

            # Check that warning was logged
            assert any(
                "did not drain" in str(call_args)
                for call_args in mock_logger.warning.call_args_list
            )

    def test_finish_run_delegates_to_run_manager(self, handler: ResultsHandler) -> None:
        """Test finish_run delegates to RunManager."""
        handler.start_session()
        handler.run_manager.start_run.return_value = 123
        handler.start_run()

        handler.publisher = Mock()
        handler.queue = Mock()
        handler.queue.join = Mock(return_value=True)

        handler.finish_run(run_id=123, status=RunStatus.ABORTED, error_message="Test error")

        handler.run_manager.finish_run.assert_called_once_with(
            status=RunStatus.ABORTED,
            error_message="Test error",
        )

    def test_finish_run_without_run_manager(self, tmp_path: Path) -> None:
        """Test finish_run returns early when no run_manager."""
        config = ProofyConfig(
            output_dir=str(tmp_path / "artifacts"),
        )

        handler = ResultsHandler(
            config=config,
            framework="pytest",
            disable_output=True,
        )

        handler.start_session()
        # Should not raise
        handler.finish_run(run_id=None, status=RunStatus.FINISHED)

    def test_finish_run_handles_flush_error(self, handler: ResultsHandler) -> None:
        """Test finish_run handles flush errors gracefully."""
        handler.start_session()
        handler.run_manager.start_run.return_value = 123
        handler.start_run()

        handler.publisher = Mock()
        handler.publisher.flush.side_effect = Exception("Flush failed")
        handler.queue = Mock()
        handler.queue.join = Mock(return_value=True)

        # Should not raise
        handler.finish_run(run_id=123, status=RunStatus.FINISHED)

        handler.run_manager.finish_run.assert_called_once()


class TestResultsHandlerTestLifecycle:
    """Test ResultsHandler test lifecycle methods."""

    @pytest.fixture
    def handler(self, tmp_path: Path) -> ResultsHandler:
        """Create a ResultsHandler with mocked dependencies."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="live",
        )

        with patch.object(UploaderWorker, "start"):
            handler = ResultsHandler(
                config=config,
                framework="pytest",
            )
            handler.worker = Mock(spec=UploaderWorker)
            handler.publisher = Mock()

        return handler

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

    def test_on_test_started_starts_test_in_context(
        self, handler: ResultsHandler, test_result: TestResult
    ) -> None:
        """Test on_test_started registers test in context."""
        handler.start_session()
        handler.on_test_started(test_result)

        assert handler.context.get_result(test_result.id) is not None
        assert handler.context.current_test() == test_result

    def test_on_test_started_creates_result_in_live_mode(
        self, handler: ResultsHandler, test_result: TestResult
    ) -> None:
        """Test on_test_started creates result immediately in live mode."""
        handler.config.mode = "live"
        handler.start_session()
        handler.on_test_started(test_result)

        handler.publisher.publish.assert_called_once_with(test_result)

    def test_on_test_started_does_not_publish_in_lazy_mode(
        self, tmp_path: Path, test_result: TestResult
    ) -> None:
        """Test on_test_started does not publish in lazy mode."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="lazy",
        )

        with patch.object(UploaderWorker, "start"):
            handler = ResultsHandler(config=config, framework="pytest")
            handler.worker = Mock(spec=UploaderWorker)
            handler.publisher = Mock()

        handler.start_session()
        handler.on_test_started(test_result)

        handler.publisher.publish.assert_not_called()

    def test_on_test_started_handles_error(
        self, handler: ResultsHandler, test_result: TestResult
    ) -> None:
        """Test on_test_started handles publisher errors gracefully."""
        handler.config.mode = "live"
        handler.start_session()
        handler.publisher.publish.side_effect = Exception("Publish failed")

        # Should not raise
        handler.on_test_started(test_result)

    def test_on_test_finished_finishes_test_in_context(
        self, handler: ResultsHandler, test_result: TestResult
    ) -> None:
        """Test on_test_finished marks test as finished in context."""
        handler.start_session()
        handler.context.start_test(test_result)
        handler.on_test_finished(test_result)

        assert handler.context.current_test() is None

    def test_on_test_finished_publishes_result(
        self, handler: ResultsHandler, test_result: TestResult
    ) -> None:
        """Test on_test_finished publishes result."""
        handler.start_session()
        handler.context.start_test(test_result)
        handler.on_test_finished(test_result)

        handler.publisher.publish.assert_called_once_with(test_result)

    def test_on_test_finished_uploads_artifacts(
        self, handler: ResultsHandler, test_result: TestResult
    ) -> None:
        """Test on_test_finished uploads artifacts."""
        handler.start_session()
        handler.context.start_test(test_result)
        handler.artifacts = Mock(spec=ArtifactUploader)

        # Add traceback to result
        test_result.traceback = "Error traceback"

        handler.on_test_finished(test_result)

        handler.artifacts.upload_traceback.assert_called_once_with(test_result)

    def test_on_test_finished_uploads_attachments(
        self, handler: ResultsHandler, test_result: TestResult, tmp_path: Path
    ) -> None:
        """Test on_test_finished uploads attachments."""
        handler.start_session()
        handler.context.start_test(test_result)
        handler.artifacts = Mock(spec=ArtifactUploader)

        # Add attachments
        attachment = Attachment(
            name="screenshot.png",
            path=str(tmp_path / "screenshot.png"),
            mime_type="image/png",
        )
        test_result.attachments.append(attachment)

        handler.on_test_finished(test_result)

        handler.artifacts.upload_attachment.assert_called_once_with(test_result, attachment)

    def test_on_test_finished_handles_upload_errors(
        self, handler: ResultsHandler, test_result: TestResult
    ) -> None:
        """Test on_test_finished handles upload errors gracefully."""
        handler.start_session()
        handler.context.start_test(test_result)
        handler.artifacts = Mock(spec=ArtifactUploader)
        handler.artifacts.upload_traceback.side_effect = Exception("Upload failed")

        test_result.traceback = "Error traceback"

        # Should not raise
        handler.on_test_finished(test_result)

    def test_get_result(self, handler: ResultsHandler, test_result: TestResult) -> None:
        """Test get_result delegates to context."""
        handler.start_session()
        handler.context.start_test(test_result)

        result = handler.get_result(test_result.id)

        assert result == test_result

    def test_get_result_not_found(self, handler: ResultsHandler) -> None:
        """Test get_result returns None for unknown ID."""
        handler.start_session()

        result = handler.get_result("unknown-id")

        assert result is None


class TestResultsHandlerFlushResults:
    """Test ResultsHandler flush_results method."""

    @pytest.fixture
    def handler(self, tmp_path: Path) -> ResultsHandler:
        """Create a ResultsHandler with mocked dependencies."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="batch",
            batch_size=10,
        )

        with patch.object(UploaderWorker, "start"):
            handler = ResultsHandler(
                config=config,
                framework="pytest",
            )
            handler.worker = Mock(spec=UploaderWorker)
            handler.publisher = Mock()

        return handler

    def test_flush_results_delegates_to_publisher(self, handler: ResultsHandler) -> None:
        """Test flush_results delegates to publisher."""
        handler.start_session()
        handler.flush_results()

        handler.publisher.flush.assert_called_once()

    def test_flush_results_without_publisher(self, tmp_path: Path) -> None:
        """Test flush_results returns early when no publisher."""
        config = ProofyConfig(
            output_dir=str(tmp_path / "artifacts"),
        )

        handler = ResultsHandler(
            config=config,
            framework="pytest",
            disable_output=True,
        )

        handler.start_session()
        # Should not raise
        handler.flush_results()


class TestResultsHandlerBackupResults:
    """Test ResultsHandler backup_results method."""

    @pytest.fixture
    def handler(self, tmp_path: Path) -> ResultsHandler:
        """Create a ResultsHandler with mocked dependencies."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="live",
        )

        with patch.object(UploaderWorker, "start"):
            handler = ResultsHandler(
                config=config,
                framework="pytest",
            )
            handler.worker = Mock(spec=UploaderWorker)

        return handler

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

    def test_backup_results_creates_json_file(
        self, handler: ResultsHandler, test_result: TestResult
    ) -> None:
        """Test backup_results creates results.json file."""
        handler.start_session()
        handler.context.start_test(test_result)
        handler.context.finish_test(test_result)

        handler.backup_results()

        results_file = handler.output_dir / "results.json"
        assert results_file.exists()

    def test_backup_results_contains_correct_data(
        self, handler: ResultsHandler, test_result: TestResult
    ) -> None:
        """Test backup_results file contains correct data."""
        handler.start_session()
        handler.context.start_test(test_result)
        handler.context.finish_test(test_result)

        handler.backup_results()

        results_file = handler.output_dir / "results.json"
        with open(results_file) as f:
            data = json.load(f)

        assert "run_name" in data
        assert "run_id" in data
        assert "run_attributes" in data
        assert "count" in data
        assert data["count"] == 1
        assert "items" in data
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == "test-1"

    def test_backup_results_with_disable_output(self, tmp_path: Path) -> None:
        """Test backup_results returns early when disable_output=True."""
        config = ProofyConfig(
            output_dir=str(tmp_path / "artifacts"),
        )

        handler = ResultsHandler(
            config=config,
            framework="pytest",
            disable_output=True,
        )

        handler.start_session()
        handler.backup_results()

        results_file = Path(config.output_dir) / "results.json"
        assert not results_file.exists()

    def test_backup_results_handles_errors(
        self, handler: ResultsHandler, test_result: TestResult
    ) -> None:
        """Test backup_results handles errors gracefully."""
        handler.start_session()
        handler.context.start_test(test_result)
        handler.context.finish_test(test_result)

        # Make output_dir unwritable
        handler.output_dir = Path("/invalid/path/that/does/not/exist")

        # Should not raise
        handler.backup_results()


class TestResultsHandlerIntegration:
    """Integration tests for ResultsHandler."""

    @pytest.fixture
    def handler(self, tmp_path: Path) -> ResultsHandler:
        """Create a ResultsHandler with real dependencies."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="live",
        )

        with (
            patch.object(UploaderWorker, "start"),
            patch.object(Client, "create_run") as mock_create,
            patch.object(Client, "create_result"),
        ):
            mock_create.return_value = {"id": 123}
            handler = ResultsHandler(
                config=config,
                framework="pytest",
            )
            handler.worker = Mock(spec=UploaderWorker)

        return handler

    def test_full_test_lifecycle(self, handler: ResultsHandler) -> None:
        """Test complete test lifecycle from session start to end."""
        # Start session
        handler.start_session()
        assert handler.context.session_ctx is not None

        # Start run
        with patch.object(handler.client, "create_run", return_value={"id": 123}):
            run_id = handler.start_run()
            assert run_id == 123

        # Start test
        test_result = TestResult(
            id="test-1",
            name="test_example",
            path="tests/test_example.py",
            test_path="tests/test_example.py",
            status=ResultStatus.PASSED,
            test_identifier="tests/test_example.py::test_example",
            run_id=123,
        )

        with patch.object(handler.client, "create_result", return_value={"id": 1}):
            handler.on_test_started(test_result)

        assert handler.context.current_test() == test_result

        # Finish test
        with patch.object(handler.client, "update_result"):
            handler.on_test_finished(test_result)

        assert handler.context.current_test() is None

        # Finish run
        handler.queue = Mock()
        handler.queue.join = Mock(return_value=True)

        with patch.object(handler.client, "update_run"):
            handler.finish_run(run_id=123, status=RunStatus.FINISHED)

        # End session
        handler.end_session()
        assert handler.context.session_ctx is None

    def test_batch_mode_lifecycle(self, tmp_path: Path) -> None:
        """Test batch mode collects and flushes results."""
        config = ProofyConfig(
            api_base="https://api.proofy.io",
            token="test-token",
            project_id=1,
            output_dir=str(tmp_path / "artifacts"),
            mode="batch",
            batch_size=3,
        )

        with patch.object(UploaderWorker, "start"):
            handler = ResultsHandler(
                config=config,
                framework="pytest",
            )
            handler.worker = Mock(spec=UploaderWorker)
            # Mock the client methods
            handler.client.create_run = Mock(return_value={"id": 123})
            handler.client.create_result = Mock(return_value={"id": 1})

        handler.start_session()
        handler.start_run()

        # Add tests but don't reach batch threshold
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
            handler.context.start_test(result)
            handler.context.finish_test(result)
            handler.on_test_finished(result)

        # Results should be buffered
        assert len(handler.buffer) == 2
        assert handler.client.create_result.call_count == 0

        # Manual flush should send them
        handler.flush_results()
        assert len(handler.buffer) == 0
        assert handler.client.create_result.call_count == 2
