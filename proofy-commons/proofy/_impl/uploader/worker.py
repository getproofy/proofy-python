"""Async uploader worker running in a background thread."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from ...core.client.async_client import AsyncClient
from .queue import (
    CreateResultJob,
    CreateRunJob,
    StopJob,
    UpdateResultJob,
    UpdateRunJob,
    UploadArtifactJob,
    UploadQueue,
)

logger = logging.getLogger("ProofyUploader")


class WorkerMetrics:
    """Tracks worker performance metrics."""

    def __init__(self) -> None:
        self.jobs_processed = 0
        self.jobs_failed = 0
        self.jobs_retried = 0
        self.bytes_uploaded = 0
        self.total_duration_s = 0.0
        self.start_time = time.monotonic()

    def record_success(self, duration_s: float, bytes_uploaded: int = 0) -> None:
        """Record a successful job."""
        self.jobs_processed += 1
        self.total_duration_s += duration_s
        self.bytes_uploaded += bytes_uploaded

    def record_failure(self) -> None:
        """Record a failed job."""
        self.jobs_failed += 1

    def record_retry(self) -> None:
        """Record a retry attempt."""
        self.jobs_retried += 1

    def get_stats(self) -> dict[str, Any]:
        """Get current statistics."""
        elapsed = time.monotonic() - self.start_time
        return {
            "jobs_processed": self.jobs_processed,
            "jobs_failed": self.jobs_failed,
            "jobs_retried": self.jobs_retried,
            "bytes_uploaded": self.bytes_uploaded,
            "avg_latency_ms": (
                (self.total_duration_s / self.jobs_processed * 1000)
                if self.jobs_processed > 0
                else 0
            ),
            "throughput_jobs_per_sec": self.jobs_processed / elapsed if elapsed > 0 else 0,
            "throughput_mbps": (
                (self.bytes_uploaded / (1024 * 1024)) / elapsed if elapsed > 0 else 0
            ),
            "uptime_s": elapsed,
        }


class UploaderWorker:
    """Background worker that processes upload jobs using AsyncClient.

    This worker runs an asyncio event loop in a dedicated thread, consuming
    jobs from a thread-safe queue and executing them asynchronously.
    """

    def __init__(
        self,
        queue: UploadQueue,
        base_url: str,
        token: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        fail_open: bool = True,
    ) -> None:
        """Initialize the uploader worker.

        Args:
            queue: Thread-safe job queue
            base_url: Base URL for Proofy API
            token: Optional bearer token
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            fail_open: If True, errors don't crash the worker
        """
        self.queue = queue
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self.fail_open = fail_open

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = threading.Event()
        self._client: AsyncClient | None = None

        self.metrics = WorkerMetrics()

    def start(self) -> None:
        """Start the worker thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Worker already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="ProofyUploader")
        self._thread.start()
        logger.info("Uploader worker started")

    def stop(self, timeout: float | None = 10.0) -> None:
        """Stop the worker thread gracefully.

        Args:
            timeout: Maximum time to wait for worker to stop (seconds)
        """
        if self._thread is None or not self._thread.is_alive():
            logger.debug("Worker not running")
            return

        logger.info("Stopping uploader worker...")
        # Send stop job
        self.queue.put(StopJob())
        self._stop_event.set()

        # Wait for thread to finish
        self._thread.join(timeout=timeout)

        if self._thread.is_alive():
            logger.warning(f"Worker did not stop within {timeout}s")
        else:
            logger.info("Uploader worker stopped")

    def _run_loop(self) -> None:
        """Run the asyncio event loop in this thread."""
        try:
            # Create new event loop for this thread
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # Run the async worker
            self._loop.run_until_complete(self._worker_loop())
        except Exception as e:
            logger.error(f"Worker loop crashed: {e}", exc_info=True)
        finally:
            # Cleanup
            if self._loop:
                self._loop.close()
            self._loop = None

    async def _worker_loop(self) -> None:
        """Main async worker loop that processes jobs."""
        # Create async client
        self._client = AsyncClient(
            base_url=self.base_url,
            token=self.token,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )

        try:
            while not self._stop_event.is_set():
                # Get next job from queue (with timeout to check stop event)
                try:
                    job = await asyncio.get_event_loop().run_in_executor(
                        None, self.queue.get, True, 0.5
                    )
                except Exception:
                    # Timeout or queue empty, continue
                    continue

                # Check for stop sentinel
                if isinstance(job, StopJob):
                    logger.debug("Received stop job")
                    self.queue.task_done()
                    break

                # Process job
                start_time = time.monotonic()
                try:
                    bytes_uploaded = await self._process_job(job)
                    duration = time.monotonic() - start_time
                    self.metrics.record_success(duration, bytes_uploaded)
                except Exception as e:
                    self.metrics.record_failure()
                    if self.fail_open:
                        logger.error(f"Job failed: {e}", exc_info=True)
                    else:
                        raise
                finally:
                    self.queue.task_done()

        finally:
            # Close client
            if self._client:
                await self._client.close()
                self._client = None

    async def _process_job(self, job: Any) -> int:
        """Process a single job.

        Args:
            job: Job to process

        Returns:
            Number of bytes uploaded (0 for non-upload jobs)
        """
        if not self._client:
            raise RuntimeError("Client not initialized")

        if isinstance(job, CreateRunJob):
            await self._client.create_run(
                project_id=job.project_id,
                name=job.name,
                started_at=job.started_at,
                attributes=job.attributes,
            )
            return 0

        elif isinstance(job, UpdateRunJob):
            await self._client.update_run(
                run_id=job.run_id,
                name=job.name,
                status=job.status,
                ended_at=job.ended_at,
                attributes=job.attributes,
            )
            return 0

        elif isinstance(job, CreateResultJob):
            await self._client.create_result(
                run_id=job.run_id,
                name=job.name,
                path=job.path,
                status=job.status,
                started_at=job.started_at,
                ended_at=job.ended_at,
                duration_ms=job.duration_ms,
                message=job.message,
                attributes=job.attributes,
            )
            return 0

        elif isinstance(job, UpdateResultJob):
            await self._client.update_result(
                run_id=job.run_id,
                result_id=job.result_id,
                status=job.status,
                ended_at=job.ended_at,
                duration_ms=job.duration_ms,
                message=job.message,
                attributes=job.attributes,
            )
            return 0

        elif isinstance(job, UploadArtifactJob):
            try:
                result = await self._client.upload_artifact_file(
                    run_id=job.run_id,
                    result_id=job.result_id,
                    file=job.file,
                    filename=job.filename,
                    mime_type=job.mime_type,
                    size_bytes=job.size_bytes,
                    hash_sha256=job.hash_sha256,
                    type=job.type,
                )

                # Invoke success callback if provided
                if job.on_success:
                    try:
                        if asyncio.iscoroutinefunction(job.on_success):
                            await job.on_success(result)
                        else:
                            job.on_success(result)
                    except Exception as e:
                        logger.warning(f"Success callback failed: {e}")

                return job.size_bytes

            except Exception as e:
                # Invoke error callback if provided
                if job.on_error:
                    try:
                        if asyncio.iscoroutinefunction(job.on_error):
                            await job.on_error(e)
                        else:
                            job.on_error(e)
                    except Exception as callback_err:
                        logger.warning(f"Error callback failed: {callback_err}")
                raise

        else:
            logger.warning(f"Unknown job type: {type(job)}")
            return 0

    def get_metrics(self) -> dict[str, Any]:
        """Get current worker metrics."""
        stats = self.metrics.get_stats()
        stats["queue_size"] = self.queue.qsize()
        stats["running"] = self._thread is not None and self._thread.is_alive()
        return stats


__all__ = ["UploaderWorker", "WorkerMetrics"]
