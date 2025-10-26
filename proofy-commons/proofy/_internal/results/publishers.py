"""Result publishing strategies for different modes.

This module implements the Strategy pattern for result publishing,
with separate implementations for live, lazy, and batch modes.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ...core.client import Client
from ...core.models import ReportingStatus, TestResult
from ...core.utils import format_datetime_rfc3339
from ..context import ContextService
from .limits import (
    MESSAGE_LIMIT,
    NAME_LIMIT,
    PATH_LIMIT,
    TEST_IDENTIFIER_LIMIT,
    clamp_string,
)
from .result_buffer import ResultBuffer
from .utils import merge_metadata

logger = logging.getLogger("ProofyPublisher")


class BaseResultPublisher(ABC):
    """Base class for result publishing strategies.

    Each subclass implements a different strategy for sending results
    to the Proofy API based on the configured mode.
    """

    def __init__(self, client: Client, context: ContextService) -> None:
        """Initialize publisher.

        Args:
            client: API client for result operations
            context: Context service for accessing test state
        """
        self.client = client
        self.context = context

    @abstractmethod
    def publish(self, result: TestResult) -> None:
        """Publish a test result.

        Args:
            result: Test result to publish
        """
        raise NotImplementedError

    @abstractmethod
    def flush(self) -> None:
        """Flush any pending results.

        Called at the end of the run to ensure all results are sent.
        """
        raise NotImplementedError

    def _send_result(self, result: TestResult) -> int | None:
        """Send a test result to the API (create).

        Args:
            result: Test result to send

        Returns:
            Result ID if successful, None otherwise
        """
        if result.run_id is None:
            logger.error("Cannot send test result without run_id")
            return None

        try:
            # Validate test_identifier length
            if len(result.test_identifier) > TEST_IDENTIFIER_LIMIT:
                raise ValueError(
                    f"test_identifier exceeds limit of {TEST_IDENTIFIER_LIMIT} characters. "
                    f"Got {len(result.test_identifier)} characters."
                )

            # Convert datetime to RFC3339 string
            started_at_str = (
                format_datetime_rfc3339(result.started_at) if result.started_at else None
            )
            ended_at_str = format_datetime_rfc3339(result.ended_at) if result.ended_at else None
            name = clamp_string(result.name, NAME_LIMIT, context="result.name") or result.name
            path = clamp_string(result.path, PATH_LIMIT, context="result.path") or result.path
            message = clamp_string(result.message, MESSAGE_LIMIT, context="result.message")
            test_identifier = result.test_identifier

            response = self.client.create_result(
                result.run_id,
                name=name,
                path=path,
                status=result.status,
                started_at=started_at_str,
                ended_at=ended_at_str,
                duration_ms=result.effective_duration_ms,
                message=message,
                attributes=merge_metadata(result),
                test_identifier=test_identifier,
            )

            # Extract the ID from the response dictionary
            result_id = response.get("id")
            if not isinstance(result_id, int):
                raise ValueError(
                    f"Expected integer ID in response, got {type(result_id)}: {result_id}"
                )

            result.reporting_status = ReportingStatus.INITIALIZED
            result.result_id = result_id
            return result_id

        except Exception as e:
            result.reporting_status = ReportingStatus.FAILED
            logger.error(f"Failed to send result for run {result.run_id}: {e}")
            return None

    def _update_result(self, result: TestResult) -> bool:
        """Update a test result in the API.

        Args:
            result: Test result to update

        Returns:
            True if successful, False otherwise
        """
        if result.run_id is None or result.result_id is None:
            logger.error("Cannot update test result without run_id and result_id")
            return False

        try:
            # Convert datetime to RFC3339 string
            ended_at_str = format_datetime_rfc3339(result.ended_at) if result.ended_at else None
            message = clamp_string(result.message, MESSAGE_LIMIT, context="result.message")

            self.client.update_result(
                result.run_id,
                result.result_id,
                status=result.status,
                ended_at=ended_at_str,
                duration_ms=result.effective_duration_ms,
                message=message,
                attributes=merge_metadata(result),
            )

            result.reporting_status = ReportingStatus.FINISHED
            return True

        except Exception as e:
            result.reporting_status = ReportingStatus.FAILED
            logger.error(f"Failed to update result {result.result_id} for run {result.run_id}: {e}")
            return False


class LivePublisher(BaseResultPublisher):
    """Publisher for live mode: creates result at start, updates at finish.

    In live mode, results are sent to the API immediately at both
    test start and test finish for real-time visibility.
    """

    def publish(self, result: TestResult) -> None:
        """Publish result immediately (create or update based on state).

        Args:
            result: Test result to publish
        """
        if not result.result_id:
            # Create result at start
            result_id = self._send_result(result)
            if result_id is not None:
                result.result_id = result_id
                result.reporting_status = ReportingStatus.INITIALIZED
        else:
            # Update result at finish
            if result.reporting_status == ReportingStatus.INITIALIZED:
                self._update_result(result)

    def flush(self) -> None:
        """No-op in live mode: all results sent immediately."""
        pass


class LazyPublisher(BaseResultPublisher):
    """Publisher for lazy mode: collects all results, sends at end.

    In lazy mode, results are collected during test execution and
    sent to the API only when flush() is called at the end of the run.
    """

    def publish(self, result: TestResult) -> None:
        """Store result for later sending.

        Args:
            result: Test result to buffer
        """
        pass

    def flush(self) -> None:
        """Send all collected results to the API."""
        results = self.context.get_results()
        for result in results.values():
            result_id = self._send_result(result)
            if result_id is None:
                result.reporting_status = ReportingStatus.FAILED
            else:
                result.reporting_status = ReportingStatus.FINISHED


class BatchPublisher(BaseResultPublisher):
    """Publisher for batch mode: sends results in configurable batches.

    In batch mode, results are buffered and sent in batches when
    the buffer reaches a threshold size, balancing latency and throughput.
    """

    def __init__(
        self,
        client: Client,
        context: ContextService,
        buffer: ResultBuffer,
    ) -> None:
        """Initialize batch publisher.

        Args:
            client: API client for result operations
            context: Context service for accessing test state
            buffer: Result buffer for batch accumulation
        """
        super().__init__(client, context)
        self.buffer = buffer

    def publish(self, result: TestResult) -> None:
        """Add result to buffer and flush if threshold reached.

        Args:
            result: Test result to publish
        """
        self.buffer.add_result(result.id)
        if self.buffer.should_flush():
            self.flush()

    def flush(self) -> None:
        """Send all pending results in the buffer."""
        if not self.buffer.pending:
            return

        for result_id in self.buffer.get_pending():
            result = self.context.get_result(result_id)
            if result is None:
                logger.warning(f"Skipping missing result {result_id} during batch send.")
                continue

            sent_id = self._send_result(result)
            if sent_id is None:
                result.reporting_status = ReportingStatus.FAILED
            else:
                result.reporting_status = ReportingStatus.FINISHED

        self.buffer.clear()
