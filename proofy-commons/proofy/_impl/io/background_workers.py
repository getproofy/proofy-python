"""Background worker pool for concurrent processing of results and attachments."""

from __future__ import annotations

import concurrent.futures
import logging
import threading
from collections.abc import Callable
from typing import Any

from ..config import WorkerConfig

logger = logging.getLogger("ProofyConductor")


class BackgroundWorkerPool:
    """Thread pool for background processing of results and attachments."""

    def __init__(self, config: WorkerConfig):
        self.config = config
        self._result_executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._attachment_executor: concurrent.futures.ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self._shutdown = False

    def start(self) -> None:
        """Start background worker pools."""
        with self._lock:
            if self._shutdown:
                raise RuntimeError("Cannot start worker pool after shutdown")

            if self._result_executor is None:
                self._result_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=self.config.max_workers,
                    thread_name_prefix="proofy-result",
                )
                logger.debug(f"Started result worker pool with {self.config.max_workers} workers")

            if self._attachment_executor is None:
                self._attachment_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=self.config.max_attachment_workers,
                    thread_name_prefix="proofy-attachment",
                )
                logger.debug(
                    f"Started attachment worker pool with {self.config.max_attachment_workers} workers"
                )

    def submit_result_task(self, func: Callable, *args, **kwargs) -> concurrent.futures.Future:
        """Submit a result processing task."""
        if self._shutdown:
            raise RuntimeError("Cannot submit tasks after shutdown")

        if self._result_executor is None:
            self.start()

        return self._result_executor.submit(func, *args, **kwargs)

    def submit_attachment_task(self, func: Callable, *args, **kwargs) -> concurrent.futures.Future:
        """Submit an attachment upload task."""
        if self._shutdown:
            raise RuntimeError("Cannot submit tasks after shutdown")

        if self._attachment_executor is None:
            self.start()

        return self._attachment_executor.submit(func, *args, **kwargs)

    def shutdown(self, timeout: float = 30.0) -> None:
        """Shutdown worker pools gracefully."""
        with self._lock:
            if self._shutdown:
                return

            self._shutdown = True

            # Shutdown result executor
            if self._result_executor:
                logger.debug("Shutting down result worker pool")
                self._result_executor.shutdown(wait=True)
                self._result_executor = None

            # Shutdown attachment executor
            if self._attachment_executor:
                logger.debug("Shutting down attachment worker pool")
                self._attachment_executor.shutdown(wait=True)
                self._attachment_executor = None

            logger.debug("Background worker pools shutdown complete")

    def is_running(self) -> bool:
        """Check if worker pools are running."""
        with self._lock:
            return not self._shutdown and (
                self._result_executor is not None or self._attachment_executor is not None
            )

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the worker pools."""
        with self._lock:
            stats = {
                "shutdown": self._shutdown,
                "result_workers": self.config.max_workers,
                "attachment_workers": self.config.max_attachment_workers,
            }

            if self._result_executor:
                stats["result_pool_active"] = True
            else:
                stats["result_pool_active"] = False

            if self._attachment_executor:
                stats["attachment_pool_active"] = True
            else:
                stats["attachment_pool_active"] = False

            return stats

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown()


__all__ = [
    "BackgroundWorkerPool",
]
