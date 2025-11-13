"""Internal ResultsHandler for run creation, result delivery and backups.

This module provides a facade over the result handling subsystem, delegating
to specialized components for run management, result publishing, and artifact handling.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..._internal.config import ProofyConfig
from ...core.client import Client
from ...core.models import RunStatus, TestResult
from ...core.system_info import collect_system_attributes, get_framework_version
from ...core.utils import now_rfc3339
from ..artifacts import ArtifactUploader
from ..constants import PredefinedAttribute
from ..context import get_context_service
from ..uploader import UploaderWorker, UploadQueue
from .limits import clamp_attributes
from .publishers import BatchPublisher, LazyPublisher, LivePublisher
from .result_buffer import ResultBuffer
from .run_manager import RunManager

logger = logging.getLogger("Proofy")


class ResultsHandler:
    """Facade for run lifecycle, result publishing, and artifact uploads.

    Delegates to specialized components:
    - RunManager: run lifecycle (create, update, finalize)
    - Publishers: result publishing strategies (live/lazy/batch)
    - ArtifactUploader: async artifact uploads (uses prepare_attachment functions)
    """

    def __init__(
        self,
        *,
        config: ProofyConfig,
        framework: str,
        disable_output: bool = False,
    ) -> None:
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.framework = framework
        self.disable_output = disable_output

        # Initialize client, queue, and worker if API configured
        self.client: Client | None = None
        self.queue: UploadQueue | None = None
        self.worker: UploaderWorker | None = None

        if not self.disable_output:
            missing_config = []
            if not config.api_base:
                missing_config.append("api_base")
            if not config.token:
                missing_config.append("token")
            if not config.project_id:
                missing_config.append("project_id")
            if missing_config:
                raise RuntimeError(
                    f"Missing Proofy required configuration: {', '.join(missing_config)}"
                )
            self.client = Client(
                base_url=config.api_base,
                token=config.token,
                timeout=config.timeout_s,
            )
            self.queue = UploadQueue(maxsize=1000)
            self.worker = UploaderWorker(
                queue=self.queue,
                base_url=config.api_base,
                token=config.token,
                timeout=config.timeout_s,
                max_retries=3,
                fail_open=True,
                max_concurrent_uploads=config.max_concurrent_uploads,
            )
            self.worker.start()

        # Initialize context service
        self.context = get_context_service()

        # Initialize components
        self.run_manager: RunManager | None = None
        self.publisher: LivePublisher | LazyPublisher | BatchPublisher | None = None
        self.buffer: ResultBuffer | None = None

        # Initialize artifact uploader with queue and config (if available)
        if self.queue:
            self.artifacts: ArtifactUploader | None = ArtifactUploader(
                queue=self.queue,
                config=config,
            )
        else:
            self.artifacts = None

        if self.client:
            # Initialize run manager
            self.run_manager = RunManager(self.client, self.context)

            # Initialize result publisher based on mode
            # Publishers now handle artifact uploads as part of their strategy
            if self.config.mode == "batch":
                self.buffer = ResultBuffer(config.batch_size)
                self.publisher = BatchPublisher(
                    self.client, self.context, self.buffer, artifact_uploader=self.artifacts
                )
            elif self.config.mode == "lazy":
                self.publisher = LazyPublisher(
                    self.client, self.context, artifact_uploader=self.artifacts
                )
            else:  # live mode
                self.publisher = LivePublisher(
                    self.client, self.context, artifact_uploader=self.artifacts
                )

    def get_result(self, id: str) -> TestResult | None:
        return self.context.get_result(id)

    # --- Run lifecycle (delegated to RunManager) ---
    def start_run(self) -> int | None:
        """Start a new run, using data from session context.

        Returns:
            Run ID if run was created, None if client not configured
        """
        session = self.context.session_ctx
        if not session:
            raise RuntimeError("Session not initialized. Call start_session() first.")

        if not self.run_manager:
            return session.run_id

        if self.config.project_id is None:
            raise RuntimeError("Proofy project_id is required to create a run")

        # Delegate to RunManager
        run_id = self.run_manager.start_run(
            project_id=self.config.project_id,
            name=session.run_name or f"Run {now_rfc3339()}",
            attributes=session.run_attributes,
        )
        return run_id

    def start_session(
        self,
        run_id: int | None = None,
    ) -> None:
        """Start a session and prepare run metadata in session context.

        - Initializes the in-process session context
        - Computes and stores run_name in session (defaults if not provided)
        - Computes and stores run_attributes in session (system + user)

        Args:
            run_id: Optional run ID (if continuing existing run)
        """
        # Determine effective run name
        effective_run_name = self.config.run_name or f"Test run {self.framework}-{now_rfc3339()}"

        # Build run attributes: system + user-provided
        system_attrs = collect_system_attributes()
        system_attrs[PredefinedAttribute.FRAMEWORK.value] = self.framework
        if framework_version := get_framework_version(self.framework):
            system_attrs[PredefinedAttribute.FRAMEWORK_VERSION.value] = framework_version
        user_attrs = self.config.run_attributes or {}
        prepared_run_attrs = clamp_attributes({**system_attrs, **user_attrs})

        # Initialize session with prepared name/attributes
        self.context.start_session(
            run_id=run_id,
            config=self.config,
            run_name=effective_run_name,
            run_attributes=prepared_run_attrs,
        )

    def finish_run(
        self,
        *,
        run_id: int | None,
        status: RunStatus = RunStatus.FINISHED,
        error_message: str | None = None,
    ) -> None:
        """Finalize a run with final status and attributes.

        Args:
            run_id: Optional run ID (defaults to session run_id)
            status: Final run status
            error_message: Optional error message to add to run attributes
        """
        if not self.run_manager:
            return

        # Flush pending results before finalizing
        try:
            self.flush_results()
        except Exception as e:
            logger.error(f"Failed to flush results: {e}")

        # Wait for queue to drain if using async worker
        if self.queue:
            logger.debug("Waiting for upload queue to drain...")
            if not self.queue.join(timeout=60.0):
                logger.warning("Upload queue did not drain within 60s")

        # Clamp final attributes before sending
        final_attrs = clamp_attributes(self.context.get_run_attributes().copy())
        # Update context with clamped attributes
        for key, value in final_attrs.items():
            self.context.set_run_attribute(key, value)

        # Delegate to RunManager
        self.run_manager.finish_run(
            status=status,
            error_message=error_message,
        )

    def end_session(self) -> None:
        """End the session and stop the worker if running."""
        # Stop worker gracefully
        if self.worker:
            logger.debug("Stopping uploader worker...")
            self.worker.stop(timeout=10.0)
            # Log final metrics
            if hasattr(self.worker, "get_metrics"):
                metrics = self.worker.get_metrics()
                logger.debug(f"Uploader metrics: {metrics}")

        self.context.end_session()

    # --- Result handling (delegated to Publishers) ---
    def on_test_started(self, result: TestResult) -> None:
        """Handle test start: create server-side result in live mode.

        Args:
            result: Test result being started
        """
        # Start test in context
        self.context.start_test(result=result)

        # In live mode, create result immediately
        if self.config.mode == "live" and self.publisher:
            try:
                self.publisher.publish(result)
            except Exception as e:
                logger.error(f"Failed to create result in live mode: {e}")

    def on_test_finished(self, result: TestResult) -> None:
        """Publish finished result according to mode.

        Args:
            result: Finished test result
        """
        # Finish test in context
        self.context.finish_test(result=result)

        # Delegate to publisher (which handles artifact uploads)
        if self.publisher:
            self.publisher.publish(result)

    def flush_results(self) -> None:
        """Flush any pending results (delegated to Publisher).

        Publishers handle both result sending and artifact uploads.
        In live mode, this is a no-op as results are sent immediately.
        """
        if self.publisher:
            self.publisher.flush()

    # --- Local backups ---
    def backup_results(self) -> None:
        if self.disable_output:
            return
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            results_file = self.output_dir / "results.json"
            items = [r.to_dict() for r in self.context.get_results().values()]
            run_attributes = self.context.get_run_attributes()
            run_name = self.context.get_run_name()
            run_id = self.context.get_run_id()

            payload = {
                "run_name": run_name,
                "run_id": run_id,
                "run_attributes": run_attributes,
                "count": len(items),
                "items": items,
            }
            with open(results_file, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            logger.info(f"Results backed up to {results_file}")
        except Exception as e:
            logger.error(f"Failed to backup results locally: {e}")
