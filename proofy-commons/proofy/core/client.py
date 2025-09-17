"""Unified Proofy API client combining both project approaches."""

from __future__ import annotations

import json
import logging
import urllib.parse
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

import requests

from .models import ResultStatus, RunStatus, TestResult

logger = logging.getLogger(__name__)


def format_datetime_rfc3339(dt: datetime | str) -> str:
    """Format datetime to RFC 3339 format."""
    if isinstance(dt, str):
        return dt  # Already formatted, assume it's correct

    if dt.tzinfo is None:
        # Assume UTC if no timezone info
        return dt.isoformat() + "Z"
    else:
        # Use timezone-aware formatting
        return dt.isoformat()


class ProofyDataEncoder(json.JSONEncoder):
    """Custom JSON encoder for Proofy data types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return format_datetime_rfc3339(obj)
        elif isinstance(obj, Path):
            return str(obj)
        return super().default(obj)


class ProofyClient:
    """Unified Proofy API client supporting both sync and async patterns.

    Combines the simple send-based API (current project) with the
    create/update-based API (old project) that returns server IDs.
    """

    HEADERS = {"Content-Type": "application/json", "Accept": "*/*"}

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        api_key: str | None = None,  # Legacy compatibility
        timeout_s: float = 10.0,
    ) -> None:
        """Initialize the Proofy client.

        Args:
            base_url: Base URL for the Proofy API
            token: Bearer token for authentication (preferred)
            api_key: API key for authentication (legacy compatibility)
            timeout_s: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

        # Setup session
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "proofy-python-unified/0.1.0", **self.HEADERS})

        # Authentication - prefer token over api_key
        auth_token = token or api_key
        if auth_token:
            self.session.headers.update({"Authorization": f"Bearer {auth_token}"})

    # ========== Current Project API (send-based, for compatibility) ==========

    def send_test_result(self, result: TestResult) -> dict[str, Any]:
        """Send a single test result (current project compatibility)."""
        if result.server_id and result.run_id:
            # If we have server_id, this is an update
            return self.update_test_result(
                run_id=result.run_id,
                result_id=result.server_id,
                status=result.status or self._outcome_to_status(result.outcome),
                ended_at=result.ended_at or datetime.now(),
                duration_ms=int(result.effective_duration_ms or 0),
                message=result.message or result.traceback,
                attributes=result.merge_metadata(),
            )
        else:
            # New result - create it
            url = f"{self.base_url}/results"
            payload = result.to_dict()
            response = self.session.post(url, json=payload, timeout=self.timeout_s)
            return response.json()  # type: ignore[no-any-return]

    def send_test_results(self, results: Iterable[TestResult]) -> requests.Response:
        """Send multiple test results in batch (current project compatibility)."""
        url = f"{self.base_url}/results/batch"
        payload: list[dict[str, Any]] = [r.to_dict() for r in results]
        return self.session.post(url, json=payload, timeout=self.timeout_s)

    def get_presigned_url(self, filename: str) -> requests.Response:
        """Get presigned URL for attachment upload (current project)."""
        url = f"{self.base_url}/attachments/presign"
        payload = {"filename": filename}
        return self.session.post(url, json=payload, timeout=self.timeout_s)

    def confirm_attachment(self, attachment_id: str) -> requests.Response:
        """Confirm attachment upload (current project)."""
        url = f"{self.base_url}/attachments/{attachment_id}/confirm"
        return self.session.post(url, timeout=self.timeout_s)

    # ========== Old Project API (create/update-based, returns server IDs) ==========

    def create_test_run(
        self,
        project: int,
        name: str,
        status: RunStatus,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new test run and return its details including ID."""
        return cast(
            dict[str, Any],
            self._send_request(
                "POST",
                "/v1/runs",
                data={
                    "project_id": project,
                    "name": name,
                    "started_at": format_datetime_rfc3339(datetime.now()),
                    "attributes": attributes or {},
                },
            ).json(),
        )

    def update_test_run(
        self,
        run_id: int,
        status: RunStatus,
        ended_at: str | datetime,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing test run."""
        return cast(
            dict[str, Any],
            self._send_request(
                "PATCH",
                f"/v1/runs/{run_id}",
                data={
                    "status": status,
                    "ended_at": format_datetime_rfc3339(ended_at),
                    "attributes": attributes or {},
                },
            ).json(),
        )

    def create_test_result(
        self,
        run_id: int,
        display_name: str,
        path: str,
        status: int | ResultStatus | None = None,
        started_at: str | datetime | None = None,
        ended_at: str | datetime | None = None,
        duration_ms: int = 0,
        message: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        """Create a new test result and return its server-assigned ID."""
        if not run_id:
            raise ValueError("Run id cannot be None.")

        data: dict[str, Any] = {
            "name": display_name,
            "path": path,
            "attributes": attributes or {},
        }

        # Add optional fields only if provided
        if status is not None:
            data["status"] = status
        if started_at is not None:
            data["started_at"] = format_datetime_rfc3339(started_at)
        if ended_at is not None:
            data["ended_at"] = format_datetime_rfc3339(ended_at)
        if duration_ms > 0:
            data["duration_ms"] = duration_ms
        if message:
            data["message"] = message

        response = self._send_request(
            "POST",
            f"/v1/runs/{int(run_id)}/results",
            data=data,
        )
        result_id = response.json().get("id")
        if not result_id:
            raise ValueError("Server did not return a result ID")
        return int(result_id)

    def create_test_result_batches(
        self, run_id: int, results: list[TestResult]
    ) -> list[dict[str, Any]]:
        """Create multiple test results in batch and return their IDs."""
        items: list[dict[str, Any]] = []
        for result in results:
            item: dict[str, Any] = {
                "name": result.name,
                "path": result.path,
                "attributes": result.merge_metadata(),
            }

            # Add optional fields
            if result.status is not None:
                item["status"] = result.status
            elif result.outcome:
                item["status"] = self._outcome_to_status(result.outcome)

            if result.started_at:
                item["started_at"] = format_datetime_rfc3339(result.started_at)
            if result.ended_at:
                item["ended_at"] = format_datetime_rfc3339(result.ended_at)
            if result.effective_duration_ms:
                item["duration_ms"] = int(result.effective_duration_ms)
            if result.message or result.traceback:
                item["message"] = result.message or result.traceback

            items.append(item)

        response = self._send_request(
            "POST", f"/v1/runs/{run_id}/results/batch", data={"items": items}
        )
        return response.json().get("items", [])  # type: ignore[no-any-return]

    def update_test_result(
        self,
        run_id: int,
        result_id: int,
        status: int | ResultStatus | None = None,
        ended_at: str | datetime | None = None,
        duration_ms: int | None = None,
        message: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing test result."""
        data: dict[str, Any] = {}

        # Add only provided fields
        if status is not None:
            data["status"] = status
        if ended_at is not None:
            data["ended_at"] = format_datetime_rfc3339(ended_at)
        if duration_ms is not None:
            data["duration_ms"] = duration_ms
        if message is not None:
            data["message"] = message
        if attributes:
            data["attributes"] = attributes

        return cast(
            dict[str, Any],
            self._send_request(
                "PATCH",
                f"/v1/runs/{run_id}/results/{result_id}",
                data=data,
            ).json(),
        )

    def get_presigned_upload_url(self, filename: str, content_type: str) -> dict[str, Any]:
        """Get presigned URL for S3 upload."""
        url = f"{self.base_url}/v1/attachments/presign"
        payload = {"filename": filename, "content_type": content_type}
        response = self._send_request("POST", url, data=payload)
        return response.json()  # type: ignore[no-any-return]

    def confirm_attachment_upload(self, attachment_id: str, result_id: int) -> dict[str, Any]:
        """Confirm attachment was uploaded and link to result."""
        url = f"{self.base_url}/v1/attachments/{attachment_id}/confirm"
        payload = {"result_id": result_id}
        response = self._send_request("POST", url, data=payload)
        return response.json()  # type: ignore[no-any-return]

    def upload_attachment_s3(
        self,
        result_id: int,
        file_name: str,
        file_path: str | Path,
        content_type: str,
    ) -> dict[str, Any]:
        """Upload attachment using new S3 presigned URL workflow."""
        try:
            # 1. Get presigned URL
            presign_resp = self.get_presigned_upload_url(
                filename=file_name, content_type=content_type
            )

            # 2. Upload to S3
            upload_url = presign_resp["upload_url"]
            with open(file_path, "rb") as f:
                upload_response = requests.put(upload_url, data=f.read())
                upload_response.raise_for_status()

            # 3. Confirm upload
            attachment_id = presign_resp["attachment_id"]
            return self.confirm_attachment_upload(attachment_id, result_id)

        except Exception as e:
            logger.error(f"Failed to upload attachment {file_name}: {e}")
            raise

    def batch_update_results(self, run_id: int, updates: list[dict[str, Any]]) -> dict[str, Any]:
        """Batch update multiple results (future feature)."""
        url = f"/v1/runs/{run_id}/results/batch"
        payload = {"updates": updates}
        response = self._send_request("PATCH", url, data=payload)
        return response.json()  # type: ignore[no-any-return]

    # ========== Utility Methods ==========

    @staticmethod
    def join_url(*args: str) -> str:
        """Join multiple URL components."""
        if len(args) == 0:
            return ""
        if len(args) == 1:
            return args[0]

        base = args[0]
        for path in args[1:]:
            base = urllib.parse.urljoin(base, path)
        return base

    def _send_request(
        self,
        method: Literal["GET", "OPTIONS", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
        url: str,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        files: list[Any] | None = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send HTTP request with proper error handling."""
        full_url = self.join_url(self.base_url, url)

        # Prepare headers
        request_headers = self.HEADERS.copy()
        if headers is not None:
            request_headers.update(headers)
        auth_header = self.session.headers.get("Authorization", "")
        if isinstance(auth_header, str):
            request_headers.update({"Authorization": auth_header})

        # Prepare data
        json_data = None
        if data and not files:
            json_data = json.dumps(data, cls=ProofyDataEncoder)

        try:
            response = requests.request(
                method=method,
                url=full_url,
                data=json_data if json_data else None,
                json=data if not json_data and not files else None,
                headers=request_headers,
                files=files,
                timeout=self.timeout_s,
                **kwargs,
            )
            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending request to Proofy API: {e}")
            if hasattr(e, "response") and e.response is not None:
                content = e.response.content
                if isinstance(content, bytes):
                    content = content.decode("utf-8", errors="replace")
                logger.error(f"Response content: {content}")
            raise

    def _outcome_to_status(self, outcome: str | None) -> ResultStatus:
        """Convert outcome string to ResultStatus enum."""
        if not outcome:
            return ResultStatus.IN_PROGRESS

        mapping = {
            "passed": ResultStatus.PASSED,
            "failed": ResultStatus.FAILED,
            "error": ResultStatus.BROKEN,
            "skipped": ResultStatus.SKIPPED,
        }
        return mapping.get(outcome.lower(), ResultStatus.IN_PROGRESS)
