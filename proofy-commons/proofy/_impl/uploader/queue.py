"""Thread-safe job queue for upload operations."""

from __future__ import annotations

import queue
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...core.client.base import ArtifactType


@dataclass
class StopJob:
    """Sentinel job to signal worker shutdown."""

    priority: int = 0


@dataclass
class CreateRunJob:
    """Job to create a run."""

    project_id: int
    name: str
    priority: int = 0
    started_at: str | None = None
    attributes: dict[str, Any] | None = None


@dataclass
class UpdateRunJob:
    """Job to update a run."""

    run_id: int
    priority: int = 0
    name: str | None = None
    status: int | None = None
    ended_at: str | None = None
    attributes: dict[str, Any] | None = None


@dataclass
class CreateResultJob:
    """Job to create a test result."""

    run_id: int
    name: str
    path: str
    priority: int = 0
    status: int | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    message: str | None = None
    attributes: dict[str, Any] | None = None


@dataclass
class UpdateResultJob:
    """Job to update a test result."""

    run_id: int
    result_id: int
    priority: int = 0
    status: int | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    message: str | None = None
    attributes: dict[str, Any] | None = None


@dataclass
class UploadArtifactJob:
    """Job to upload an artifact (attachment, traceback, etc)."""

    run_id: int
    result_id: int
    file: str | Path | bytes
    filename: str
    mime_type: str
    size_bytes: int
    hash_sha256: str
    priority: int = 0
    type: ArtifactType | int = ArtifactType.OTHER
    # Optional: callback to invoke after upload completes
    on_success: Any = None  # Callable or None
    on_error: Any = None  # Callable or None


Job = StopJob | CreateRunJob | UpdateRunJob | CreateResultJob | UpdateResultJob | UploadArtifactJob


class UploadQueue:
    """Thread-safe queue for upload jobs.

    This queue uses Python's queue.PriorityQueue internally to support
    job prioritization while maintaining thread safety.
    """

    def __init__(self, maxsize: int = 0) -> None:
        """Initialize the upload queue.

        Args:
            maxsize: Maximum number of items in queue (0 = unlimited)
        """
        # Use PriorityQueue to support job priorities
        self._queue: queue.PriorityQueue[tuple[int, int, Job]] = queue.PriorityQueue(maxsize)
        self._counter = 0  # To break ties in priority

    def put(self, job: Job, block: bool = True, timeout: float | None = None) -> None:
        """Add a job to the queue.

        Args:
            job: Job to add
            block: Whether to block if queue is full
            timeout: Timeout in seconds (None = wait forever)
        """
        # Priority queue uses (priority, counter, item) tuples
        # Counter ensures FIFO ordering within same priority
        self._queue.put((job.priority, self._counter, job), block=block, timeout=timeout)
        self._counter += 1

    def get(self, block: bool = True, timeout: float | None = None) -> Job:
        """Get a job from the queue.

        Args:
            block: Whether to block if queue is empty
            timeout: Timeout in seconds (None = wait forever)

        Returns:
            Next job from queue
        """
        _, _, job = self._queue.get(block=block, timeout=timeout)
        return job

    def task_done(self) -> None:
        """Mark a task as done (for join() to work)."""
        self._queue.task_done()

    def join(self, timeout: float | None = None) -> bool:
        """Block until all tasks are done.

        Args:
            timeout: Timeout in seconds (None = wait forever)

        Returns:
            True if all tasks completed, False if timeout occurred
        """
        if timeout is None:
            self._queue.join()
            return True
        else:
            # PriorityQueue doesn't support timeout in join, use workaround
            import time

            deadline = time.monotonic() + timeout
            while self._queue.unfinished_tasks > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                time.sleep(min(0.1, remaining))
            return True

    def qsize(self) -> int:
        """Return approximate queue size."""
        return self._queue.qsize()

    def empty(self) -> bool:
        """Return True if queue is empty."""
        return self._queue.empty()

    def full(self) -> bool:
        """Return True if queue is full."""
        return self._queue.full()


__all__ = [
    "CreateResultJob",
    "CreateRunJob",
    "Job",
    "StopJob",
    "UpdateResultJob",
    "UpdateRunJob",
    "UploadArtifactJob",
    "UploadQueue",
]
