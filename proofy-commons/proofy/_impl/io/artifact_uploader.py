"""Artifact uploading utilities extracted from ResultsHandler.

This module centralizes logic for uploading attachments and tracebacks,
keeping network I/O concerns in one place and enabling easier testing.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
from typing import Any

from ...core.client import ArtifactType, ProofyClient
from ...core.models import Attachment, TestResult
from ..export.attachments import is_cached_path

logger = logging.getLogger("ProofyConductor")


class ArtifactUploader:
    """Upload artifacts (attachments, tracebacks) related to test results."""

    def __init__(self, client: ProofyClient | None) -> None:
        self.client = client

    def upload_attachment(
        self, result: TestResult, attachment: Attachment | dict[str, Any]
    ) -> None:
        """Upload a single attachment for a given result.

        Best-effort: computes MIME when missing and removes cached files on success.
        """
        try:
            if not self.client:
                return

            # Accept both dataclass Attachment and dict payloads
            if isinstance(attachment, dict):
                name = attachment.get("name") or attachment.get("filename")
                path = attachment.get("path")
                mime_type = attachment.get("mime_type")
                size_bytes = attachment.get("size_bytes")
                sha256 = attachment.get("_sha256") or attachment.get("sha256")
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

            guessed, _ = mimetypes.guess_type(path)
            effective_mime = mime_type or guessed or "application/octet-stream"

            if not result.run_id or not result.result_id:
                raise RuntimeError("Cannot upload attachment without run_id and result_id.")

            # Prefer fast path with known size/hash via high-level helper
            if size_bytes is not None and sha256 is not None:
                resp = self.client.upload_artifact_file(  # type: ignore[union-attr]
                    run_id=result.run_id,
                    result_id=result.result_id,
                    file=path,
                    filename=name,
                    mime_type=effective_mime,
                    size_bytes=int(size_bytes),
                    hash_sha256=str(sha256),
                    type=ArtifactType.ATTACHMENT,
                )
            else:
                # Let client compute size/hash as needed
                resp = self.client.upload_artifact(  # type: ignore[union-attr]
                    run_id=result.run_id,
                    result_id=result.result_id,
                    filename=name,
                    mime_type=effective_mime,
                    file=path,
                    type=ArtifactType.ATTACHMENT,
                )

            # Optionally record remote id when available
            artifact_id = (resp or {}).get("artifact_id")
            if (
                artifact_id
                and not isinstance(attachment, dict)
                and hasattr(attachment, "remote_id")
            ):
                attachment.remote_id = str(artifact_id)  # type: ignore[attr-defined]

            try:
                success = False
                if isinstance(resp, dict):
                    status_code = resp.get("status_code")
                    if (
                        artifact_id
                        or isinstance(status_code, int)
                        and status_code
                        in (
                            200,
                            201,
                            204,
                        )
                    ):
                        success = True
                attach_path_str = path if isinstance(path, str) else str(path)
                if success and is_cached_path(attach_path_str):
                    Path(attach_path_str).unlink(missing_ok=True)
            except Exception:
                pass

        except Exception:
            raise

    def upload_traceback(self, result: TestResult) -> None:
        """Upload a textual traceback for a failed test, if any."""
        try:
            if not self.client:
                return
            if not result.traceback:
                return
            if not result.run_id or not result.result_id:
                return

            base_name = result.name or result.path or result.id or "test"
            safe_name = "".join(
                c if (c.isalnum() or c in ("-", "_")) else "_" for c in str(base_name)
            )
            filename = f"{safe_name[:64]}-traceback.txt"

            data_bytes = result.traceback.encode("utf-8", errors="replace")

            self.client.upload_artifact(  # type: ignore[union-attr]
                run_id=result.run_id,
                result_id=result.result_id,
                file=data_bytes,
                filename=filename,
                mime_type="text/plain",
                type=ArtifactType.TRACE,
            )
        except Exception:
            raise
