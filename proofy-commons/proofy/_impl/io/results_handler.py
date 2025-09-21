"""Internal ResultsHandler for run creation, result delivery and backups.

This module centralizes I/O concerns (API calls and local backups) separate
from the pytest plugin. It depends only on commons models and client.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any

from ...core.client import ProofyClient, now_rfc3339
from ...core.models import (
    Attachment,
    ReportingStatus,
    RunStatus,
    TestResult,
)
from ...export.attachments import create_artifacts_zip
from ..context import get_context_service

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

    def get_result(self, id: str) -> TestResult | None:
        return self.context.get_result(id)

    # --- Run lifecycle ---
    def on_run_start(
        self,
        *,
        framework: str,
        run_name: str | None,
        run_id: int | None,
    ) -> int | None:
        try:
            if not self.client or not self.project_id:
                return None

            name = run_name or f"Test run {framework}-{now_rfc3339()}"

            try:
                if run_id:
                    raise RuntimeError(f"Update run {run_id} is not implemented yet")
                    self.client.update_test_run(
                        run_id=run_id,
                        status=RunStatus.STARTED,
                        attributes={
                            "framework": framework,
                        },
                    )
                else:
                    response = self.client.create_test_run(
                        project=self.project_id,
                        name=name,
                        status=RunStatus.STARTED,
                        attributes={
                            "framework": framework,
                        },
                    )
                    run_id = response.get("id")
                    if not run_id:
                        raise RuntimeError(
                            f"Failed to create run {name} for project {self.project_id}: {response.text}"
                        )
            except Exception as e:
                if run_id:
                    logger.error(
                        f"Run {name!r} update failed for project {self.project_id}: {e}",
                        exc_info=True,
                    )
                    raise RuntimeError(
                        f"Run {name!r} update failed for project {self.project_id}: {e}"
                    )
                else:
                    logger.error(
                        f"Run {name!r} creation failed for project {self.project_id}: {e}",
                        exc_info=True,
                    )
                    raise RuntimeError(
                        f"Run {name!r} creation failed for project {self.project_id}: {e}"
                    )
        finally:
            self.context.start_session(run_id=run_id)
        return run_id

    def on_run_finish(
        self,
        *,
        run_id: int | None,
    ) -> None:
        try:
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
                self.client.update_test_run(
                    run_id=run_id,
                    status=RunStatus.FINISHED,
                    ended_at=now_rfc3339(),
                    attributes={
                        "total_results": len(self._results),
                    },
                )
            except Exception as e:
                raise RuntimeError(f"Failed to finalize run: {e}")
        finally:
            pass
            # self.context.end_session()

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
            result_id = self.client.create_test_result(
                run_id=result.run_id,
                name=result.name,
                path=result.path,
                status=result.status,
                started_at=result.started_at,
                ended_at=result.ended_at,
                duration_ms=result.effective_duration_ms,
                message=result.message,
                attributes=result.merge_metadata(),
            )
        except Exception as e:
            result.reporting_status = ReportingStatus.FAILED
            logger.error(f"Failed to send result for run {result.run_id}: {e}")
            raise RuntimeError(f"Failed to send result for run {result.run_id}: {e}")
        else:
            result.reporting_status = ReportingStatus.FINISHED
            result.result_id = result_id
            return result_id

    def update_test_result(self, result: TestResult) -> None:
        try:
            self.client.update_test_result(
                run_id=result.run_id,
                result_id=result.result_id,
                status=result.status,
                ended_at=result.ended_at,
                duration_ms=result.effective_duration_ms,
                message=result.message,
                attributes=result.merge_metadata(),
            )
        except Exception as e:
            result.reporting_status = ReportingStatus.FAILED
            logger.error(f"Failed to update result {result.result_id} for run {result.run_id}: {e}")
            raise RuntimeError(
                f"Failed to update result {result.result_id} for run {result.run_id}: {e}"
            )
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
                raise RuntimeError(f"Failed to send result in live mode: {e}")
            return None

        # Update at finish
        if result.result_id and result.reporting_status == ReportingStatus.INITIALIZED:
            try:
                self.update_test_result(result)

                # Upload attachments (best-effort)
                for attachment in result.attachments:
                    self._upload_attachment(result, attachment)

            except Exception as e:
                result.reporting_status = ReportingStatus.FAILED
                logger.exception(f"Failed to send result in live mode: {e}")
                raise RuntimeError(f"Failed to send result in live mode: {e}")
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
                for attachment in result.attachments:
                    try:
                        self._upload_attachment(result, attachment)
                    except Exception as e:
                        logger.error(f"Failed to upload attachment in lazy mode: {e}")

    def _store_result_batch(self, result: TestResult) -> None:
        self._batch_results.append(result.id)
        self.context.finish_test(result=result)
        batch_size = os.environ.get("PROOFY_BATCH_SIZE", 100)
        if len(self._batch_results) >= batch_size:
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
                for attachment in result.attachments:
                    try:
                        self._upload_attachment(result, attachment)
                    except Exception as e:
                        logger.error(f"Failed to upload attachment in batch mode: {e}")
        self._batch_results = []

    def flush_results(self) -> None:
        if self.mode == "batch":
            self.send_batch()
        elif self.mode == "lazy":
            self.send_result_lazy()
        else:
            raise ValueError(f"Invalid mode: {self.mode}")

    def _upload_attachment(self, result: TestResult, attachment: Attachment) -> None:
        try:
            if getattr(attachment, "remote_id", None):
                return
            guessed, _ = mimetypes.guess_type(attachment.path)
            effective_mime = attachment.mime_type or guessed or "application/octet-stream"
            self.client.upload_attachment_s3(  # type: ignore[union-attr]
                result_id=int(result.server_id),
                file_name=attachment.name,
                file_path=attachment.path,
                content_type=effective_mime,
            )
        except Exception as e:
            print(f"Failed to upload attachment {attachment.name}: {e}")

    # --- Local backups ---
    def backup_results(self) -> None:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            data = [r.to_dict() for r in self.context.get_results().values()]
            results_file = self._results_path_for_current_process()
            with open(results_file, "w") as f:
                json.dump({"count": len(data), "items": data}, f, indent=2, default=str)
            logger.info(f"Results backed up to {results_file}")
        except Exception as e:
            logger.error(f"Failed to backup results locally: {e}")

    def merge_worker_results(self) -> None:
        try:
            # Only meaningful for master process (no PYTEST_XDIST_WORKER)
            import os

            if os.environ.get("PYTEST_XDIST_WORKER"):
                return

            all_results: list[dict[str, Any]] = []
            worker_files = list(self.output_dir.glob("results_gw*.json"))
            for wf in worker_files:
                try:
                    with open(wf) as f:
                        all_results.extend(json.load(f))
                except Exception as e:
                    print(f"Failed to read worker results from {wf}: {e}")

            if all_results:
                main_file = self.output_dir / "results.json"
                with open(main_file, "w") as f:
                    json.dump(
                        {"count": len(all_results), "items": all_results},
                        f,
                        indent=2,
                        default=str,
                    )
                print(
                    f"Merged {len(all_results)} results from {len(worker_files)} workers to {main_file}"
                )
                for wf in worker_files:
                    wf.unlink()

                # Create zip archive when backups are always enabled (caller decides)
                create_artifacts_zip(self.output_dir)
        except Exception as e:
            print(f"Failed to merge worker results: {e}")

    def _results_path_for_current_process(self) -> Path:
        import os

        worker_id = os.environ.get("PYTEST_XDIST_WORKER")
        if worker_id:
            return self.output_dir / f"results_{worker_id}.json"
        return self.output_dir / "results.json"
