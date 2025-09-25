"""Proofy API client"""

from __future__ import annotations

import hashlib
import json
import mimetypes
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import IO, Any, Literal, cast

import requests

from .models import ResultStatus, RunStatus
from .utils import format_datetime_rfc3339


class ArtifactType(int, Enum):
    """Artifact type values per API.md."""

    TRACE = 1
    SCREENSHOT = 2
    LOG = 3
    VIDEO = 4
    ATTACHMENT = 5
    OTHER = 6


@dataclass(frozen=True)
class PresignUpload:
    """Information needed to perform the object upload to storage."""

    method: Literal["PUT"]
    url: str
    headers: Mapping[str, str]
    expires_at: str


class ProofyClient:
    """Pure client for the `/v1` Proofy API."""

    DEFAULT_HEADERS: Mapping[str, str] = {
        "Accept": "*/*",
        "User-Agent": "proofy-python-0.1.0/client",
    }

    def __init__(
        self, base_url: str, token: str | None = None, timeout_s: float = 10.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.session = requests.Session()
        self.session.headers.update(dict(self.DEFAULT_HEADERS))
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    # ============================== Helpers ===============================
    @staticmethod
    def _normalize(value: Any) -> Any:
        """Convert datetimes, paths, and enums to JSON-serializable primitives."""
        if isinstance(value, datetime):
            # Ensure timezone-aware and RFC 3339 encoding
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return format_datetime_rfc3339(value)
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {k: ProofyClient._normalize(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [ProofyClient._normalize(v) for v in value]
        return value

    def _url(self, path: str) -> str:
        return (
            f"{self.base_url}{path}"
            if path.startswith("/")
            else f"{self.base_url}/{path}"
        )

    def _request(
        self,
        method: Literal["GET", "POST", "PATCH"],
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> requests.Response:
        url = self._url(path)
        merged_headers = dict(self.session.headers)
        if headers:
            merged_headers.update(headers)
        body = None if json_body is None else self._normalize(json_body)
        response = self.session.request(
            method=method,
            url=url,
            json=body,
            headers=merged_headers,
            timeout=self.timeout_s,
        )
        response.raise_for_status()
        return response

    @staticmethod
    def _stringify_attributes(attributes: dict[str, Any]) -> dict[str, str]:
        """Coerce attribute keys and values to strings, JSON-encoding complex values.

        - Keys are converted using str()
        - Values:
          - str → unchanged
          - dict/list/tuple/set → json.dumps(..., default=str)
          - other → str(value)
        Datetimes, Enums, Paths inside values are normalized via _normalize first.
        """
        normalized = ProofyClient._normalize(attributes)
        result: dict[str, str] = {}
        for key, value in cast(dict[str, Any], normalized).items():
            key_str = str(key)
            if isinstance(value, str):
                result[key_str] = value
            elif isinstance(value, dict | list | tuple | set):
                result[key_str] = json.dumps(value, default=str)
            else:
                result[key_str] = str(value)
        return result

    def health(self) -> str:
        """Check service health; returns the response text (expected: "ok")."""
        response = self._request("GET", "/health")
        return response.text

    # ============================= Runs =============================
    def create_run(
        self,
        *,
        project_id: int,
        name: str,
        started_at: datetime | str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a run (POST /v1/runs) and return JSON.

        The server defaults `started_at` to now if omitted and sets status to STARTED.
        """
        data: dict[str, Any] = {
            "project_id": int(project_id),
            "name": name,
        }
        if started_at is not None:
            data["started_at"] = started_at
        if attributes:
            data["attributes"] = self._stringify_attributes(attributes)

        return cast(
            dict[str, Any], self._request("POST", "/v1/runs", json_body=data).json()
        )

    def update_run(
        self,
        run_id: int,
        *,
        name: str | None = None,
        status: RunStatus | int | None = None,
        ended_at: datetime | str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        """Update a run (PATCH /v1/runs/{run_id}). Returns status code (expected 204).

        Rules enforced client-side to reduce server errors:
        - If `status` is provided, `ended_at` must also be provided.
        - If `ended_at` is provided, `status` must also be provided.
        - At least one updatable field must be present.
        """
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if status is not None:
            body["status"] = status
        if ended_at is not None:
            body["ended_at"] = ended_at
        if attributes:
            body["attributes"] = self._stringify_attributes(attributes)

        if ("status" in body) ^ ("ended_at" in body):
            raise ValueError("Both 'status' and 'ended_at' must be provided together.")
        if not body:
            raise ValueError("No fields to update were provided.")

        response = self._request("PATCH", f"/v1/runs/{int(run_id)}", json_body=body)
        return response.status_code

    # ============================ Results ============================
    def create_result(
        self,
        run_id: int,
        *,
        name: str,
        path: str,
        status: ResultStatus | int | None = None,
        started_at: datetime | str | None = None,
        ended_at: datetime | str | None = None,
        duration_ms: int | None = None,
        message: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a result (POST /v1/runs/{run_id}/results) and return JSON."""
        data: dict[str, Any] = {
            "name": name,
            "path": path,
        }
        if status is not None:
            data["status"] = status
        if started_at is not None:
            data["started_at"] = started_at
        if ended_at is not None:
            data["ended_at"] = ended_at
        if duration_ms is not None and duration_ms >= 0:
            data["duration_ms"] = int(duration_ms)
        if message is not None:
            data["message"] = message
        if attributes:
            data["attributes"] = self._stringify_attributes(attributes)

        return cast(
            dict[str, Any],
            self._request(
                "POST", f"/v1/runs/{int(run_id)}/results", json_body=data
            ).json(),
        )

    def update_result(
        self,
        run_id: int,
        result_id: int,
        *,
        status: ResultStatus | int | None = None,
        ended_at: datetime | str | None = None,
        duration_ms: int | None = None,
        message: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        """Update a result (PATCH /v1/runs/{run_id}/results/{result_id}). Returns status code (expected 204)."""
        body: dict[str, Any] = {}
        if status is not None:
            body["status"] = status
        if ended_at is not None:
            body["ended_at"] = ended_at
        if duration_ms is not None:
            if duration_ms < 0:
                raise ValueError("'duration_ms' must be >= 0 when provided.")
            body["duration_ms"] = int(duration_ms)
        if message is not None:
            body["message"] = message
        if attributes:
            body["attributes"] = self._stringify_attributes(attributes)

        if not body:
            raise ValueError("No fields to update were provided.")
        if ("status" in body) and ("ended_at" not in body):
            raise ValueError("Setting a terminal 'status' requires 'ended_at'.")

        response = self._request(
            "PATCH", f"/v1/runs/{int(run_id)}/results/{int(result_id)}", json_body=body
        )
        return response.status_code

    # ============================ Artifacts ===========================
    def presign_artifact(
        self,
        run_id: int,
        result_id: int,
        *,
        filename: str,
        mime_type: str,
        size_bytes: int,
        hash_sha256: str,
        type: ArtifactType | int = ArtifactType.OTHER,
    ) -> dict[str, Any]:
        """Presign an artifact upload (POST /v1/.../artifacts/presign) and return JSON."""
        if size_bytes <= 0:
            raise ValueError("'size_bytes' must be > 0.")
        data: dict[str, Any] = {
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": int(size_bytes),
            "hash_sha256": hash_sha256,
            "type": type,
        }
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                f"/v1/runs/{int(run_id)}/results/{int(result_id)}/artifacts/presign",
                json_body=data,
            ).json(),
        )

    def finalize_artifact(
        self, run_id: int, result_id: int, artifact_id: int
    ) -> tuple[int, dict[str, Any]]:
        """Finalize an artifact. Returns (status_code, json_or_empty_dict)."""
        response = self._request(
            "POST",
            f"/v1/runs/{int(run_id)}/results/{int(result_id)}/artifacts/{int(artifact_id)}/finalize",
        )
        try:
            return response.status_code, cast(dict[str, Any], response.json())
        except ValueError:
            # .json() raises ValueError on invalid JSON across requests versions
            return response.status_code, {}

    # ============================ Convenience =========================
    def upload_artifact(
        self,
        run_id: int,
        result_id: int,
        *,
        file: str | Path | bytes | bytearray | memoryview | IO[bytes],
        filename: str | None = None,
        mime_type: str | None = None,
        type: ArtifactType | int = ArtifactType.OTHER,
    ) -> dict[str, Any]:
        """Upload an artifact by auto-computing size, MIME type, and SHA-256.

        - `file`: path, bytes-like, or binary stream. If a path is provided and
          `filename` is omitted, the basename of the path is used.
        - `filename`: optional; required when `file` is not a path to help guess MIME.
        - `mime_type`: optional; if omitted, guessed from `filename`.
        - `type`: artifact type enum or int.
        """
        # Determine filename
        inferred_filename: str | None = None
        if isinstance(file, str | Path):
            inferred_filename = Path(file).name
        final_filename = filename or inferred_filename
        if not final_filename:
            raise ValueError("'filename' is required when 'file' is not a path")

        # Guess MIME type if not provided
        final_mime = mime_type or (
            mimetypes.guess_type(final_filename)[0] or "application/octet-stream"
        )

        # Compute size and sha256
        if isinstance(file, str | Path):
            path = Path(file)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            size_bytes = int(path.stat().st_size)
            sha256 = hashlib.sha256()
            with path.open("rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    sha256.update(chunk)
            digest = sha256.hexdigest()
            source_for_upload: Any = path
        elif isinstance(file, bytes | bytearray | memoryview):
            buf = bytes(file)
            size_bytes = len(buf)
            digest = hashlib.sha256(buf).hexdigest()
            source_for_upload = buf
        else:
            # file-like stream
            stream: IO[bytes] = file
            # If seekable, preserve position
            pos = None
            try:
                pos = stream.tell()
            except Exception:
                pos = None
            sha256 = hashlib.sha256()
            total = 0
            # Read and hash
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                sha256.update(chunk)
            digest = sha256.hexdigest()
            size_bytes = total
            # Reset stream if possible, else fallback to bytes
            try:
                if pos is not None:
                    stream.seek(pos)
                    source_for_upload = stream
                else:
                    # Build bytes to upload
                    raise Exception("non-seekable stream")
            except Exception as err:
                # We already consumed; re-materialize into memory once
                # Note: caller should prefer seekable streams for large files
                data_bytes = getattr(stream, "getvalue", lambda: None)()
                if data_bytes is None:
                    # As a last resort, cannot recover; instruct caller
                    raise ValueError(
                        "Non-seekable stream provided; pass bytes or a seekable stream."
                    ) from err
                source_for_upload = data_bytes

        return self.upload_artifact_file(
            run_id,
            result_id,
            file=source_for_upload,
            filename=final_filename,
            mime_type=final_mime,
            size_bytes=size_bytes,
            hash_sha256=digest,
            type=type,
        )

    def upload_artifact_file(
        self,
        run_id: int,
        result_id: int,
        *,
        file: str | Path | bytes | bytearray | memoryview | IO[bytes],
        filename: str,
        mime_type: str,
        size_bytes: int,
        hash_sha256: str,
        type: ArtifactType | int = ArtifactType.OTHER,
    ) -> dict[str, Any]:
        """Convenience helper: presign, upload with required headers, finalize.

        The `file` parameter can be:
        - a path (`str` or `Path`) to read from disk,
        - a bytes-like object (`bytes`, `bytearray`, `memoryview`), or
        - a binary stream (`IO[bytes]`, e.g., `io.BytesIO`).

        Returns a dict with keys: `artifact_id`, `status_code`, and (optionally) `finalize`.
        """
        presign = self.presign_artifact(
            run_id,
            result_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            hash_sha256=hash_sha256,
            type=type,
        )

        upload_info = cast(dict[str, Any], presign.get("upload", {}))
        method = upload_info.get("method", "PUT")
        url = upload_info.get("url")
        headers = cast(Mapping[str, str], upload_info.get("headers", {}))
        if method != "PUT" or not url:
            raise ValueError("Invalid presign response: missing PUT upload URL.")

        # Upload based on the type of `file`
        if isinstance(file, bytes | bytearray | memoryview):
            put_resp = requests.put(url, data=file, headers=dict(headers))
            put_resp.raise_for_status()
        elif isinstance(file, str | Path):
            with open(Path(file), "rb") as f:
                put_resp = requests.put(url, data=f, headers=dict(headers))
                put_resp.raise_for_status()
        else:
            # Assume file-like binary stream
            put_resp = requests.put(url, data=file, headers=dict(headers))
            put_resp.raise_for_status()

        artifact_id = cast(int, presign.get("artifact_id"))

        status_code, finalize_json = self.finalize_artifact(
            run_id, result_id, artifact_id
        )
        return {
            "artifact_id": artifact_id,
            "status_code": status_code,
            "finalize": finalize_json,
        }
