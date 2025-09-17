"""Unified Proofy API client combining both project approaches."""

from __future__ import annotations

import json
import logging
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Union

import requests

from .models import ResultStatus, RunStatus, TestResult

logger = logging.getLogger(__name__)


def convert_dict_to_key_value(data: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert dictionary to key-value format for API compatibility."""
    if not data:
        return []
    return [{"key": str(k), "value": str(v)} for k, v in data.items()]


class ProofyDataEncoder(json.JSONEncoder):
    """Custom JSON encoder for Proofy data types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat(timespec="milliseconds").replace("+00:00", "Z")
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
        token: Optional[str] = None,
        api_key: Optional[str] = None,  # Legacy compatibility
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
        self.session.headers.update(
            {"User-Agent": "proofy-python-unified/0.1.0", **self.HEADERS}
        )

        # Authentication - prefer token over api_key
        auth_token = token or api_key
        if auth_token:
            self.session.headers.update({"Authorization": f"Bearer {auth_token}"})

    # ========== Current Project API (send-based, for compatibility) ==========

    def send_test_result(self, result: TestResult) -> requests.Response:
        """Send a single test result (current project compatibility)."""
        if result.server_id:
            # If we have server_id, this is an update
            return self.update_test_result(
                result_id=result.server_id,
                status=result.status or self._outcome_to_status(result.outcome),
                end_time=result.end_time or datetime.now(),
                duration=int(result.effective_duration_ms or 0),
                message=result.message or result.error,
                trace=result.trace or result.traceback,
                attributes=result.merge_metadata(),
            )
        else:
            # New result - create it
            url = f"{self.base_url}/results"
            payload = result.to_dict()
            return self.session.post(url, json=payload, timeout=self.timeout_s)

    def send_test_results(self, results: Iterable[TestResult]) -> requests.Response:
        """Send multiple test results in batch (current project compatibility)."""
        url = f"{self.base_url}/results/batch"
        payload: List[Dict[str, Any]] = [r.to_dict() for r in results]
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
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new test run and return its details including ID."""
        return self._send_request(
            "POST",
            "/api/v1/runs",
            data={
                "project_id": project,
                "name": name,
                "status": status,
                "attributes": convert_dict_to_key_value(attributes),
            },
        ).json()

    def update_test_run(
        self,
        run_id: int,
        status: RunStatus,
        end_time: Union[str, datetime],
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update an existing test run."""
        return self._send_request(
            "PATCH",
            f"/api/v1/runs/{run_id}",
            data={
                "status": status,
                "end_time": end_time,
                "attributes": convert_dict_to_key_value(attributes),
            },
        ).json()

    def create_test_result(
        self,
        run_id: int,
        display_name: str,
        path: str,
        status: Union[int, ResultStatus],
        start_time: Union[str, datetime],
        end_time: Union[str, datetime],
        duration: int = 0,
        message: Optional[str] = None,
        trace: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Create a new test result and return its server-assigned ID."""
        if not run_id:
            raise ValueError("Run id cannot be None.")

        response = self._send_request(
            "POST",
            f"/api/v1/runs/{int(run_id)}/results",
            data={
                "name": display_name,
                "path": path,
                "status": status,
                "start_time": start_time,
                "end_time": end_time,
                "duration": duration,
                "message": message,
                "trace": trace,
                "attributes": convert_dict_to_key_value(attributes),
            },
        )
        result_id = response.json().get("id")
        if not result_id:
            raise ValueError("Server did not return a result ID")
        return int(result_id)

    def create_test_result_batches(
        self, run_id: int, results: List[TestResult]
    ) -> List[Dict[str, Any]]:
        """Create multiple test results in batch and return their IDs."""
        items = []
        for result in results:
            items.append(
                {
                    "name": result.name,
                    "path": result.path,
                    "status": result.status or self._outcome_to_status(result.outcome),
                    "start_time": result.start_time,
                    "end_time": result.end_time,
                    "duration": int(result.effective_duration_ms or 0),
                    "message": result.message or result.error,
                    "trace": result.trace or result.traceback,
                    "attributes": convert_dict_to_key_value(result.merge_metadata()),
                }
            )

        response = self._send_request(
            "POST", f"/api/v1/runs/{run_id}/results:batch", data={"items": items}
        )
        return response.json().get("items", [])

    def update_test_result(
        self,
        result_id: int,
        status: Union[int, ResultStatus],
        end_time: Union[str, datetime],
        duration: int,
        message: Optional[str] = None,
        trace: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update an existing test result."""
        return self._send_request(
            "PATCH",
            f"/api/v1/results/{result_id}",
            data={
                "status": status,
                "duration": duration,
                "end_time": end_time,
                "message": message,
                "trace": trace,
                "attributes": convert_dict_to_key_value(attributes),
            },
        ).json()

    def add_attachment(
        self,
        result_id: int,
        file_name: str,
        file: Union[str, bytes, Path],
        content_type: str,
    ) -> Dict[str, Any]:
        """Add attachment to a test result."""
        files = []

        if isinstance(file, (str, Path)):
            # File path
            with open(file, "rb") as f:
                files.append(("file", (file_name, f, content_type)))
                response = self._send_request(
                    "POST",
                    f"/api/v1/results/{result_id}/attachments",
                    headers={},  # Remove content-type for multipart
                    files=files,
                )
        else:
            # Bytes data
            files.append(("file", (file_name, file, content_type)))
            response = self._send_request(
                "POST",
                f"/api/v1/results/{result_id}/attachments",
                headers={},  # Remove content-type for multipart
                files=files,
            )

        return response.json()

    # ========== Utility Methods ==========

    @staticmethod
    def join_url(*args: str) -> str:
        """Join multiple URL components."""
        return urllib.parse.urljoin(*args)

    def _send_request(
        self,
        method: Literal["GET", "OPTIONS", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
        url: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        files: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> requests.Response:
        """Send HTTP request with proper error handling."""
        full_url = self.join_url(self.base_url, url)

        # Prepare headers
        request_headers = self.HEADERS.copy()
        if headers is not None:
            request_headers.update(headers)
        request_headers.update(
            {"Authorization": self.session.headers.get("Authorization", "")}
        )

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
                logger.error(f"Response content: {e.response.content}")
            raise

    def _outcome_to_status(self, outcome: Optional[str]) -> ResultStatus:
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
