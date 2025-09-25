"""Internal ResultsHandler for run creation, result delivery and backups.

This module centralizes I/O concerns (API calls and local backups) separate
from the pytest plugin. It depends only on commons models and client.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from ...core.client import ProofyClient
from ...core.models import (
    ReportingStatus,
    RunStatus,
    TestResult,
)
from ...core.utils import now_rfc3339
from ..context import get_context_service
from .artifact_uploader import ArtifactUploader

logger = logging.getLogger("ProofyConductor")


# rename to ProofyConductor
class ResultsHandler:
    """Handle run lifecycle, result sending, and local backups."""

    def __init__(
        self,
        *,
        client: ProofyClient | None,
        mode: str,
        output_dir: str,
        project_id: int | None,
    ) -> None:
        self.client = client
        self.mode = mode  # "live" | "lazy" | "batch"
        self.output_dir = Path(output_dir)
        self.project_id: int | None = project_id

        # In-process accumulation for lazy/batch
        self._batch_results: list[str] = []  # test IDs
        self.context = get_context_service()
        self.artifacts = ArtifactUploader(client=self.client)

    def get_result(self, id: str) -> TestResult | None:
        return self.context.get_result(id)

    # --- Run lifecycle ---
    def start_run(
        self,
        *,
        framework: str,
        run_name: str | None,
        run_id: int | None,
    ) -> int | None:
        if not self.client or not self.project_id:
            return None

        name = run_name or f"Test run {framework}-{now_rfc3339()}"

        if run_id:
            raise RuntimeError(f"Update run {run_id} is not implemented yet")
            self.client.update_run(
                run_id=run_id,
                status=RunStatus.STARTED,
                attributes={
                    "framework": framework,
                },
            )
        else:
            try:
                response = self.client.create_run(
                    project_id=self.project_id,
                    name=name,
                    started_at=now_rfc3339(),
                    attributes={
                        "framework": framework,
                    },
                )
                run_id = response.get("id", None)
                if not run_id:
                    raise RuntimeError(
                        f"'run_id' not found in response: {json.dumps(response)}"
                    )
            except Exception as e:
                logger.error(
                    f"Run {name!r} creation failed for project {self.project_id}: {e}",
                    exc_info=True,
                )
                raise RuntimeError(
                    f"Run {name!r} creation failed for project {self.project_id}: {e}"
                ) from e

        return run_id

    def start_session(
        self, run_id: int | None = None, config: dict[str, Any] | None = None
    ) -> None:
        self.context.start_session(run_id=run_id, config=config)

    def finish_run(
        self,
        *,
        run_id: int | None,
    ) -> None:
        run_id = run_id or self.context.session_ctx.run_id
        if not self.client:
            return
        if not run_id:
            raise RuntimeError("Run ID not found. Make sure to call start_run() first.")
        try:
            self.flush_results()
        except Exception as e:
            logger.exception(f"Failed to flush results: {e}")
        try:
            self.client.update_run(
                run_id=run_id,
                name=self.context.session_ctx.run_name,
                status=RunStatus.FINISHED,
                ended_at=now_rfc3339(),
                attributes={
                    "total_results": len(self.context.get_results()),
                },
            )
        except Exception as e:
            raise RuntimeError(f"Failed to finalize run: {e}") from e

    def end_session(self) -> None:
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
                logger.exception(f"Failed to create result for live mode: {e}")
                # raise RuntimeError(f"Failed to create result for live mode: {e}")
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

    def send_test_result(self, result: TestResult) -> int:
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
            raise RuntimeError(
                f"Failed to send result for run {result.run_id}: {e}"
            ) from e
        else:
            result.reporting_status = ReportingStatus.FINISHED
            result.result_id = result_id
            return result_id

    def update_test_result(self, result: TestResult) -> None:
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
            logger.error(
                f"Failed to update result {result.result_id} for run {result.run_id}: {e}"
            )
            raise RuntimeError(
                f"Failed to update result {result.result_id} for run {result.run_id}: {e}"
            ) from e
        else:
            result.reporting_status = ReportingStatus.FINISHED

    def _store_result_live(self, result: TestResult) -> None:
        if not result.result_id:
            try:
                result_id = self.send_test_result(result)
                result.result_id = result_id
                result.reporting_status = ReportingStatus.INITIALIZED
            except Exception as e:
                logger.exception(f"Failed to send result in live mode: {e}")
                raise RuntimeError(f"Failed to send result in live mode: {e}") from e
            return None

        # Update at finish
        if result.result_id and result.reporting_status == ReportingStatus.INITIALIZED:
            try:
                self.update_test_result(result)

                # Upload attachments (best-effort)
                self.artifacts.upload_traceback(result)
                for attachment in result.attachments:
                    self.artifacts.upload_attachment(result, attachment)

            except Exception as e:
                result.reporting_status = ReportingStatus.FAILED
                logger.exception(f"Failed to send result in live mode: {e}")
                raise RuntimeError(f"Failed to send result in live mode: {e}") from e
            else:
                result.reporting_status = ReportingStatus.FINISHED
            finally:
                self.context.finish_test(result=result)

    def _store_result_lazy(self, result: TestResult) -> None:
        self.context.finish_test(result=result)

    def send_result_lazy(self) -> None:
        results = self.context.get_results()
        for result in results.values():
            try:
                self.send_test_result(result)
            except Exception as e:
                result.reporting_status = ReportingStatus.FAILED
                logger.error(f"Failed to send result in lazy mode: {e}")
            else:
                result.reporting_status = ReportingStatus.FINISHED
                try:
                    self.artifacts.upload_traceback(result)
                except Exception as e:
                    logger.error(f"Failed to upload traceback in lazy mode: {e}")
                for attachment in result.attachments:
                    try:
                        self.artifacts.upload_attachment(result, attachment)
                    except Exception as e:
                        logger.error(f"Failed to upload attachment in lazy mode: {e}")
                        raise e

    def _store_result_batch(self, result: TestResult) -> None:
        self._batch_results.append(result.id)
        self.context.finish_test(result=result)
        batch_size = os.environ.get("PROOFY_BATCH_SIZE", 100)
        if len(self._batch_results) >= int(batch_size):
            self.send_batch()

    def send_batch(self) -> None:
        if not self.client or self.mode != "batch" or not self._batch_results:
            return
        for id_ in self._batch_results:
            result = self.get_result(id_)
            try:
                self.send_test_result(result)
            except Exception as e:
                result.reporting_status = ReportingStatus.FAILED
                logger.error(f"Failed to send result in batch mode: {e}")
            else:
                result.reporting_status = ReportingStatus.FINISHED
                try:
                    self.artifacts.upload_traceback(result)
                except Exception as e:
                    logger.error(f"Failed to upload traceback in batch mode: {e}")
                for attachment in result.attachments:
                    try:
                        self.artifacts.upload_attachment(result, attachment)
                    except Exception as e:
                        logger.error(f"Failed to upload attachment in batch mode: {e}")
        self._batch_results = []

    def flush_results(self) -> None:
        if self.mode == "batch":
            self.send_batch()
        elif self.mode == "lazy":
            self.send_result_lazy()
        else:
            # live mode does not buffer; nothing to flush
            return None

    # artifact upload methods moved to ArtifactUploader

    # --- Local backups ---
    def backup_results(self) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            results_file = self.output_dir / "results.json"
            items = [r.to_dict() for r in self.context.get_results().values()]
            payload = {"count": len(items), "items": items}
            with open(results_file, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            logger.info(f"Results backed up to {results_file}")
        except Exception as e:
            logger.error(f"Failed to backup results locally: {e}")
