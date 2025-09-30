"""Concurrent processing of multiple results and attachments."""

from __future__ import annotations

import logging
from concurrent.futures import Future, as_completed
from dataclasses import dataclass
from typing import Any

from ...core.client import ProofyClient
from ...core.models import Attachment, ReportingStatus, TestResult
from ..config import WorkerConfig
from .background_workers import BackgroundWorkerPool

logger = logging.getLogger("ProofyConductor")


@dataclass
class ProcessingResult:
    """Result of concurrent processing operation."""

    completed: list[tuple[TestResult, Any]]
    failed: list[tuple[TestResult, Exception]]
    total: int

    @property
    def success_count(self) -> int:
        return len(self.completed)

    @property
    def failure_count(self) -> int:
        return len(self.failed)

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.success_count / self.total


class ConcurrentResultProcessor:
    """Handles concurrent processing of multiple results and attachments."""

    def __init__(
        self,
        worker_pool: BackgroundWorkerPool,
        client: ProofyClient,
        config: WorkerConfig,
    ):
        self.worker_pool = worker_pool
        self.client = client
        self.config = config

    def process_results_concurrently(self, results: list[TestResult]) -> ProcessingResult:
        """Process multiple results concurrently."""
        if not results:
            return ProcessingResult(completed=[], failed=[], total=0)

        logger.debug(f"Processing {len(results)} results concurrently")

        futures = []
        result_map = {}

        # Submit all result processing tasks
        for result in results:
            future = self.worker_pool.submit_result_task(self._process_single_result, result)
            futures.append(future)
            result_map[future] = result

        # Collect results as they complete
        completed_results = []
        failed_results = []

        try:
            for future in as_completed(futures, timeout=self.config.task_timeout):
                result = result_map[future]
                try:
                    result_data = future.result()
                    completed_results.append((result, result_data))
                    result.reporting_status = ReportingStatus.FINISHED
                except Exception as e:
                    logger.error(f"Failed to process result {result.id}: {e}")
                    result.reporting_status = ReportingStatus.FAILED
                    failed_results.append((result, e))
        except Exception as e:
            logger.error(f"Timeout or error during concurrent processing: {e}")
            # Mark remaining results as failed
            for future in futures:
                if not future.done():
                    result = result_map[future]
                    result.reporting_status = ReportingStatus.FAILED
                    failed_results.append((result, e))

        processing_result = ProcessingResult(
            completed=completed_results, failed=failed_results, total=len(results)
        )

        logger.info(
            f"Concurrent processing complete: {processing_result.success_count}/{processing_result.total} successful"
        )
        return processing_result

    def upload_attachments_concurrently(self, result: TestResult) -> list[Future]:
        """Upload all attachments for a result concurrently."""
        if not result.attachments:
            return []

        logger.debug(f"Uploading {len(result.attachments)} attachments for result {result.id}")

        futures = []
        for attachment in result.attachments:
            future = self.worker_pool.submit_attachment_task(
                self._upload_single_attachment, result, attachment
            )
            futures.append(future)

        return futures

    def wait_for_attachments(self, futures: list[Future]) -> dict[str, Any]:
        """Wait for attachment upload futures to complete and return results."""
        if not futures:
            return {"completed": 0, "failed": 0, "total": 0}

        completed_count = 0
        failed_count = 0

        try:
            for future in as_completed(futures, timeout=self.config.task_timeout):
                try:
                    future.result()
                    completed_count += 1
                except Exception as e:
                    logger.error(f"Attachment upload failed: {e}")
                    failed_count += 1
        except Exception as e:
            logger.error(f"Timeout or error during attachment uploads: {e}")
            # Count remaining futures as failed
            for future in futures:
                if not future.done():
                    failed_count += 1

        return {
            "completed": completed_count,
            "failed": failed_count,
            "total": len(futures),
        }

    def _process_single_result(self, result: TestResult) -> dict[str, Any]:
        """Process a single result (internal method)."""
        try:
            # Create or update the result on the server
            if not result.result_id:
                response = self.client.create_result(
                    result.run_id,
                    name=result.name,
                    path=result.path,
                    status=result.status,
                    started_at=result.started_at,
                    ended_at=result.ended_at,
                    duration_ms=result.effective_duration_ms,
                    message=result.message,
                    attributes=result.merge_metadata(),
                )
                result_id = response.get("id")
                if not isinstance(result_id, int):
                    raise ValueError(
                        f"Expected integer ID in response, got {type(result_id)}: {result_id}"
                    )
                result.result_id = result_id
            else:
                # Update existing result
                self.client.update_result(
                    result.run_id,
                    result.result_id,
                    status=result.status,
                    ended_at=result.ended_at,
                    duration_ms=result.effective_duration_ms,
                    message=result.message,
                    attributes=result.merge_metadata(),
                )

            return {"result_id": result.result_id, "status": "success"}

        except Exception as e:
            logger.error(f"Failed to process result {result.id}: {e}")
            raise

    def _upload_single_attachment(
        self, result: TestResult, attachment: Attachment
    ) -> dict[str, Any]:
        """Upload a single attachment (internal method)."""
        try:
            if not result.run_id or not result.result_id:
                raise RuntimeError("Cannot upload attachment without run_id and result_id")

            # Import here to avoid circular imports
            from .artifact_uploader import ArtifactUploader

            uploader = ArtifactUploader(self.client)
            uploader.upload_attachment(result, attachment)

            return {"attachment_name": attachment.name, "status": "success"}

        except Exception as e:
            logger.error(f"Failed to upload attachment {attachment.name}: {e}")
            raise


__all__ = [
    "ConcurrentResultProcessor",
    "ProcessingResult",
]
