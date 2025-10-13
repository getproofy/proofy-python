"""Internal ResultsHandler for run creation, result delivery and backups.

This module centralizes I/O concerns (API calls and local backups) separate
from the pytest plugin. Uses sync Client for operations that need immediate responses
and async queue/worker pattern for efficient background uploads.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from pathlib import Path

from ..._internal.config import ProofyConfig
from ...core.client import Client
from ...core.models import (
    ReportingStatus,
    RunStatus,
    TestResult,
)
from ...core.system_info import collect_system_attributes, get_framework_version
from ...core.utils import now_rfc3339
from ..artifacts import ArtifactUploader
from ..context import get_context_service
from ..uploader import UploaderWorker, UploadQueue

_DEFAULT_BATCH_SIZE = 100

logger = logging.getLogger("Proofy")


class ResultsHandler:
    """Handle run lifecycle, result sending, and local backups.

    Uses sync Client for operations requiring immediate responses (run/result creation)
    and async queue/worker for efficient background uploads (artifacts).
    """

    def __init__(
        self,
        *,
        config: ProofyConfig,
        framework: str,
        enable: bool = True,
    ) -> None:
        self.config = config
        self.mode = config.mode  # "live" | "lazy" | "batch"
        self.output_dir = Path(config.output_dir)
        self.project_id: int | None = config.project_id
        self.framework = framework
        self.enable = enable

        # Initialize client, queue, and worker if API configured
        self.client: Client | None = None
        self.queue: UploadQueue | None = None
        self.worker: UploaderWorker | None = None

        if enable:
            missing_config = []
            if not config.api_base:
                missing_config.append("api_base")
            if not config.token:
                missing_config.append("token")
            if not config.project_id:
                missing_config.append("project_id")
            if missing_config:
                logger.warning(
                    f"Missing Proofy required configuration: {', '.join(missing_config)}"
                )
            if config.api_base and config.token and config.project_id:
                self.client = Client(
                    base_url=config.api_base,
                    token=config.token,
                    timeout=config.timeout_s,
                )
                # Initialize upload queue and worker for async artifact uploads
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

        # In-process accumulation for lazy/batch
        self._batch_results: list[str] = []  # test IDs
        self.context = get_context_service()

        # Initialize artifact uploader with queue (if available)
        if self.queue:
            self.artifacts = ArtifactUploader(queue=self.queue)
        else:
            self.artifacts = None

        self._batch_size = self._resolve_batch_size()

    def get_result(self, id: str) -> TestResult | None:
        return self.context.get_result(id)

    # --- Run lifecycle ---
    def start_run(self) -> int | None:
        """Start a new run, using data from session context.

        Returns:
            Run ID if run was created, None if client not configured
        """
        session = self.context.session_ctx
        if not session:
            raise RuntimeError("Session not initialized. Call start_session() first.")

        run_id = session.run_id
        run_name = session.run_name
        run_attributes = session.run_attributes

        if not self.client or not self.project_id:
            return run_id

        if run_id:
            try:
                self.client.update_run(
                    run_id=run_id,
                    status=RunStatus.STARTED,
                    attributes=run_attributes,
                )
            except Exception as e:
                raise RuntimeError(f"Failed to update run {run_id}: {e}") from e
        else:
            try:
                response = self.client.create_run(
                    project_id=self.project_id,
                    name=run_name,
                    started_at=now_rfc3339(),
                    attributes=run_attributes,
                )
                run_id = response.get("id", None)
                if not run_id:
                    raise RuntimeError(f"'run_id' not found in response: {json.dumps(response)}")

                self.update_session_run_id(run_id)

            except Exception as e:
                raise RuntimeError(
                    f"Run {run_name!r} creation failed for project {self.project_id}: {e}"
                ) from e

        return run_id

    def update_session_run_id(self, run_id: int) -> None:
        """Update session context with run ID.

        Args:
            run_id: The run ID to set in session context
        """
        session = self.context.session_ctx
        if session:
            session.run_id = run_id

    def update_session_run_name(self, run_name: str) -> None:
        """Update session context with run name.

        Args:
            run_name: The run name to set in session context
        """
        session = self.context.session_ctx
        if session:
            session.run_name = run_name

    def start_session(
        self,
        config: ProofyConfig | None = None,
        run_id: int | None = None,
    ) -> None:
        """Start a session and prepare run metadata in session context.

        - Initializes the in-process session context
        - Computes and stores run_name in session (defaults if not provided)
        - Computes and stores run_attributes in session (system + user)

        Args:
            run_id: Optional run ID (if continuing existing run)
            config: Proofy configuration
        """
        # Determine effective run name
        effective_run_name = None
        if config and getattr(config, "run_name", None):
            effective_run_name = config.run_name  # type: ignore[attr-defined]
        else:
            # Default fallback, includes framework and timestamp
            effective_run_name = f"Test run {self.framework}-{now_rfc3339()}"

        # Build run attributes: system + user-provided
        system_attrs = collect_system_attributes()
        system_attrs["__proofy_framework"] = self.framework
        if framework_version := get_framework_version(self.framework):
            system_attrs["__proofy_framework_version"] = framework_version
        user_attrs = {}
        if config and getattr(config, "run_attributes", None):
            user_attrs = config.run_attributes or {}  # type: ignore[attr-defined]
        prepared_run_attrs = {**system_attrs, **user_attrs}

        # Initialize session with prepared name/attributes
        self.context.start_session(
            run_id=run_id,
            config=config,
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
        session = self.context.session_ctx
        run_id = run_id or (session.run_id if session else None)
        if not self.client:
            return
        if not run_id:
            logger.error("Run ID not found. Make sure to call start_run() first.")
            return
        try:
            self.flush_results()
        except Exception as e:
            logger.error(f"Failed to flush results: {e}")

        # Wait for queue to drain if using async worker
        if self.queue:
            logger.debug("Waiting for upload queue to drain...")
            if not self.queue.join(timeout=60.0):
                logger.warning("Upload queue did not drain within 60s")

        # Merge final run attributes
        if error_message is not None:
            with contextlib.suppress(Exception):
                self.context.set_run_attribute("__proofy_error_message", error_message)

        final_attrs = self.context.get_run_attributes().copy()

        try:
            self.client.update_run(
                run_id=run_id,
                name=self.context.get_run_name(),
                status=status,
                ended_at=now_rfc3339(),
                attributes=final_attrs,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to finalize run: {e}") from e

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

    # --- Result handling ---
    def on_test_started(self, result: TestResult) -> None:
        """Handle test start: create server-side result in live mode."""
        try:
            if not self.client or self.mode != "live":
                return
            if not result.run_id:
                raise ValueError("Cannot create result without run_id. ")
            try:
                self._store_result_live(result)
            except Exception as e:
                logger.error(f"Failed to create result for live mode: {e}")
        finally:
            self.context.start_test(result=result)

    def on_test_finished(self, result: TestResult) -> None:
        """Deliver or collect a finished result according to mode."""
        if self.mode == "live":
            self._store_result_live(result)
        elif self.mode == "lazy":
            self._store_result_lazy(result)
        elif self.mode == "batch":
            self._store_result_batch(result)
        else:
            raise ValueError(f"Invalid mode: {self.mode}")

    def send_test_result(self, result: TestResult) -> int | None:
        try:
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
            # Extract the ID from the response dictionary
            result_id = response.get("id")
            if not isinstance(result_id, int):
                raise ValueError(
                    f"Expected integer ID in response, got {type(result_id)}: {result_id}"
                )
        except Exception as e:
            result.reporting_status = ReportingStatus.FAILED
            logger.error(f"Failed to send result for run {result.run_id}: {e}")
            return None
        else:
            result.reporting_status = ReportingStatus.INITIALIZED
            result.result_id = result_id
            return result_id

    def update_test_result(self, result: TestResult) -> bool:
        try:
            self.client.update_result(
                result.run_id,
                result.result_id,
                status=result.status,
                ended_at=result.ended_at,
                duration_ms=result.effective_duration_ms,
                message=result.message,
                attributes=result.merge_metadata(),
            )
        except Exception as e:
            result.reporting_status = ReportingStatus.FAILED
            logger.error(f"Failed to update result {result.result_id} for run {result.run_id}: {e}")
            return False
        else:
            result.reporting_status = ReportingStatus.FINISHED
            return True

    def _store_result_live(self, result: TestResult) -> None:
        if not result.result_id:
            result_id = self.send_test_result(result)
            if result_id is not None:
                result.result_id = result_id
                result.reporting_status = ReportingStatus.INITIALIZED
            return None

        # Update at finish
        if result.result_id and result.reporting_status == ReportingStatus.INITIALIZED:
            ok = self.update_test_result(result)
            self._upload_artifacts(result, best_effort=False, mode="live")
            if ok:
                result.reporting_status = ReportingStatus.FINISHED
            self.context.finish_test(result=result)

    def _store_result_lazy(self, result: TestResult) -> None:
        self.context.finish_test(result=result)

    def send_result_lazy(self) -> None:
        results = self.context.get_results()
        for result in results.values():
            result_id = self.send_test_result(result)
            if result_id is None:
                result.reporting_status = ReportingStatus.FAILED
            else:
                result.reporting_status = ReportingStatus.FINISHED
            self._upload_artifacts(result, best_effort=True, mode="lazy")

    def _store_result_batch(self, result: TestResult) -> None:
        self._batch_results.append(result.id)
        self.context.finish_test(result=result)
        if len(self._batch_results) >= self._batch_size:
            self.send_batch()

    def send_batch(self) -> None:
        if not self.client or self.mode != "batch" or not self._batch_results:
            return
        for id_ in self._batch_results:
            result = self.get_result(id_)
            if result is None:
                logger.warning("Skipping missing result %s during batch send.", id_)
                continue
            result_id = self.send_test_result(result)
            if result_id is None:
                result.reporting_status = ReportingStatus.FAILED
            else:
                result.reporting_status = ReportingStatus.FINISHED
            self._upload_artifacts(result, best_effort=True, mode="batch")
        self._batch_results = []

    def _resolve_batch_size(self) -> int:
        raw = os.environ.get("PROOFY_BATCH_SIZE")
        if raw is None:
            return _DEFAULT_BATCH_SIZE
        try:
            value = int(raw)
        except ValueError:
            logger.warning(
                "Invalid PROOFY_BATCH_SIZE value %r. Falling back to %d.",
                raw,
                _DEFAULT_BATCH_SIZE,
            )
            return _DEFAULT_BATCH_SIZE
        if value <= 0:
            logger.warning(
                "PROOFY_BATCH_SIZE must be positive. Got %r, using %d instead.",
                raw,
                _DEFAULT_BATCH_SIZE,
            )
            return _DEFAULT_BATCH_SIZE
        return value

    def _upload_artifacts(self, result: TestResult, *, best_effort: bool, mode: str) -> None:
        if not self.artifacts:
            return
        try:
            self.artifacts.upload_traceback(result)
        except Exception as exc:
            logger.error(f"Failed to upload traceback in {mode} mode: {exc}")
        for attachment in result.attachments:
            try:
                self.artifacts.upload_attachment(result, attachment)
            except Exception as exc:
                logger.error(f"Failed to upload attachment in {mode} mode: {exc}")

    def flush_results(self) -> None:
        if self.mode == "batch":
            self.send_batch()
        elif self.mode == "lazy":
            self.send_result_lazy()
        else:
            # live mode does not buffer; nothing to flush
            return None

    # --- Local backups ---
    def backup_results(self) -> None:
        if not self.enable:
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
