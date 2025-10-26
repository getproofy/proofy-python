"""Artifact uploading utilities extracted from ResultsHandler.

This module centralizes logic for uploading attachments and tracebacks
using asynchronous queue-based uploads.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ...core.client import ArtifactType
from ...core.models import Attachment, TestResult
from ..config import ProofyConfig
from ..uploader import UploadArtifactJob, UploadQueue
from .attachments_cache import is_cached_path
from .service import prepare_traceback

logger = logging.getLogger("ProofyArtifactUploader")


class ArtifactUploader:
    """Upload artifacts (attachments, tracebacks) related to test results.

    Uses queue-based async uploads via UploadQueue + Worker for efficient
    background processing without blocking test execution.
    """

    def __init__(self, queue: UploadQueue, config: ProofyConfig) -> None:
        """Initialize artifact uploader.

        Args:
            queue: Upload queue for async uploads
            config: Proofy configuration for mode-dependent behavior
        """
        self.queue = queue
        self.config = config

    def upload_attachment(
        self, result: TestResult, attachment: Attachment | dict[str, Any]
    ) -> None:
        """Upload a single attachment for a given result.

        Attachment should already be prepared (via prepare_attachment function).
        """
        try:
            # Accept both dataclass Attachment and dict payloads
            if isinstance(attachment, dict):
                name = attachment.get("name") or attachment.get("filename")
                path = attachment.get("path")
                mime_type = attachment.get("mime_type")
                size_bytes = attachment.get("size_bytes")
                sha256 = attachment.get("_sha256") or attachment.get("sha256")
                artifact_type_val = attachment.get("artifact_type")
                if not name or not path:
                    raise ValueError("Attachment dict requires 'name' and 'path'.")
            else:
                if getattr(attachment, "remote_id", None):
                    return
                name = attachment.name
                path = attachment.path
                mime_type = attachment.mime_type
                size_bytes = attachment.size_bytes
                sha256 = attachment.sha256
                artifact_type_val = attachment.artifact_type

            if not result.run_id or not result.result_id:
                raise RuntimeError("Cannot upload attachment without run_id and result_id.")

            # Map provided artifact_type to enum or default ATTACHMENT
            final_type: ArtifactType | int = (
                ArtifactType(artifact_type_val)
                if isinstance(artifact_type_val, int)
                and artifact_type_val in {item.value for item in ArtifactType}
                else ArtifactType.ATTACHMENT
            )

            # Queue-based upload - use data directly from attachment
            # (all preparation already done by prepare_attachment() in ContextService.attach())
            self._enqueue_upload(
                result=result,
                file=path,
                filename=name,
                mime_type=mime_type or "application/octet-stream",
                size_bytes=size_bytes or 0,
                hash_sha256=sha256 or "",
                type=final_type,
                attachment=attachment if not isinstance(attachment, dict) else None,
            )

        except Exception:
            raise

    def upload_traceback(self, result: TestResult) -> None:
        """Upload a textual traceback for a failed test, if any.

        Uses prepare_traceback() function to prepare the traceback consistently.
        """
        try:
            if not result.traceback:
                return
            if not result.run_id or not result.result_id:
                return

            # Use prepare_traceback function to prepare traceback
            base_name = result.name or result.path or result.id or "test"
            prepared = prepare_traceback(
                text=result.traceback,
                base_name=base_name,
            )

            # Queue-based upload
            self._enqueue_upload(
                result=result,
                file=prepared.path,
                filename=prepared.filename,
                mime_type=prepared.mime_type,
                size_bytes=prepared.size_bytes,
                hash_sha256=prepared.sha256,
                type=prepared.artifact_type,
            )
        except Exception:
            raise

    def _enqueue_upload(
        self,
        result: TestResult,
        file: str | Path | bytes,
        filename: str,
        mime_type: str,
        size_bytes: int,
        hash_sha256: str,
        type: ArtifactType | int,
        attachment: Attachment | None = None,
    ) -> None:
        """Enqueue an artifact upload job.

        Args:
            result: Test result
            file: File path or bytes
            filename: Filename
            mime_type: MIME type
            size_bytes: File size in bytes
            hash_sha256: SHA-256 hex digest
            type: Artifact type
            attachment: Optional attachment object to update with remote_id
        """
        # Ensure identifiers are present for type narrowing
        if result.run_id is None or result.result_id is None:
            raise RuntimeError("Cannot enqueue upload without run_id and result_id.")

        run_id = result.run_id
        result_id = result.result_id

        def on_success(upload_result: dict[str, Any]) -> None:
            """Callback invoked after successful upload."""
            artifact_id = upload_result.get("artifact_id")
            if artifact_id and attachment and hasattr(attachment, "remote_id"):
                attachment.remote_id = str(artifact_id)

            # Clean up cached file
            if isinstance(file, str | Path):
                try:
                    file_path_str = str(file)
                    if is_cached_path(file_path_str):
                        Path(file_path_str).unlink(missing_ok=True)
                except Exception:
                    pass

        def on_error(error: Exception) -> None:
            """Callback invoked on upload error."""
            logger.error(f"Artifact upload failed: {error}")

        job = UploadArtifactJob(
            run_id=run_id,
            result_id=result_id,
            file=file,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            hash_sha256=hash_sha256,
            type=type,
            on_success=on_success,
            on_error=on_error,
        )

        self.queue.put(job)
