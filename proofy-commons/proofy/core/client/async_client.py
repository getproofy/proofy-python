"""Asynchronous HTTP client for Proofy API using httpx."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import random
from pathlib import Path
from typing import Any, Literal, cast

import httpx

from ..models import ResultStatus, RunStatus
from .base import (
    ArtifactType,
    ClientConfig,
    ClientHelpers,
    ProofyConnectionError,
    ProofyHTTPError,
    ProofyTimeoutError,
)

logger = logging.getLogger("ProofyClient.Async")


class AsyncRetryConfig:
    """Configuration for async retry logic."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt number using exponential backoff with full jitter."""
        delay = min(self.base_delay * (self.exponential_base**attempt), self.max_delay)
        if self.jitter:
            delay = random.uniform(0, delay)
        return delay


def should_retry_async(response: httpx.Response | None, exception: Exception | None) -> bool:
    """Determine if a request should be retried based on response or exception."""
    if exception:
        # Retry on timeout and connection errors
        return isinstance(exception, httpx.TimeoutException | httpx.ConnectError | httpx.ReadError)

    if response and (response.status_code == 429 or 500 <= response.status_code < 600):
        # Retry on 429 (rate limit) and 5xx server errors
        return True

    return False


def get_retry_after_async(response: httpx.Response) -> float | None:
    """Extract Retry-After header value in seconds."""
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None

    try:
        return float(retry_after)
    except ValueError:
        return None


class AsyncClient:
    """Asynchronous Proofy API client using httpx.AsyncClient."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float | httpx.Timeout = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        **kwargs: Any,
    ) -> None:
        """Initialize asynchronous client.

        Args:
            base_url: Base URL for the Proofy API
            token: Optional bearer token for authentication
            timeout: Request timeout (float for all timeouts, or httpx.Timeout object)
            max_retries: Maximum number of retry attempts
            retry_delay: Base delay between retries in seconds
            **kwargs: Additional httpx.AsyncClient arguments
        """
        timeout_obj = httpx.Timeout(timeout) if isinstance(timeout, float | int) else timeout

        self.config = ClientConfig(
            base_url=base_url,
            token=token,
            timeout=timeout_obj,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        self.retry_config = AsyncRetryConfig(max_retries=max_retries, base_delay=retry_delay)

        # Create httpx async client with connection pooling and HTTP/2
        self._client = httpx.AsyncClient(
            timeout=self.config.timeout,
            headers=self.config.headers,
            http2=self.config.http2,
            limits=httpx.Limits(
                max_keepalive_connections=self.config.max_keepalive,
                max_connections=self.config.max_connections,
            ),
            **kwargs,
        )

    async def __aenter__(self) -> AsyncClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _request(
        self,
        method: Literal["GET", "POST", "PATCH", "PUT"],
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
        retry: bool = True,
    ) -> httpx.Response:
        """Make an async HTTP request with retry logic.

        Args:
            method: HTTP method
            path: API path (relative to base_url)
            json_body: Optional JSON body
            content: Optional raw content
            headers: Optional additional headers
            retry: Whether to retry on failure

        Returns:
            httpx.Response object

        Raises:
            ProofyHTTPError: On HTTP error
            ProofyTimeoutError: On timeout
            ProofyConnectionError: On connection error
        """
        url = ClientHelpers.build_url(self.config.base_url, path)
        merged_headers = dict(self._client.headers)
        if headers:
            merged_headers.update(headers)

        body = None if json_body is None else ClientHelpers.normalize(json_body)

        attempt = 0
        last_exception: Exception | None = None

        while attempt <= (self.retry_config.max_retries if retry else 0):
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    json=body,
                    content=content,
                    headers=merged_headers,
                )

                # Check if we should retry based on status code
                if (
                    retry
                    and should_retry_async(response, None)
                    and attempt < self.retry_config.max_retries
                ):
                    # Respect Retry-After header if present
                    retry_after = get_retry_after_async(response)
                    delay = retry_after if retry_after else self.retry_config.get_delay(attempt)

                    logger.warning(
                        f"Request failed with status {response.status_code}, "
                        f"retrying in {delay:.2f}s (attempt {attempt + 1}/{self.retry_config.max_retries})"
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue

                # Raise on error status
                ClientHelpers.handle_http_error(response)
                return response

            except httpx.TimeoutException as e:
                last_exception = e
                if retry and attempt < self.retry_config.max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    logger.warning(
                        f"Request timeout, retrying in {delay:.2f}s "
                        f"(attempt {attempt + 1}/{self.retry_config.max_retries})"
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise ProofyTimeoutError(f"Request timed out after {attempt + 1} attempts") from e

            except (httpx.ConnectError, httpx.ReadError) as e:
                last_exception = e
                if retry and attempt < self.retry_config.max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    logger.warning(
                        f"Connection error, retrying in {delay:.2f}s "
                        f"(attempt {attempt + 1}/{self.retry_config.max_retries})"
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise ProofyConnectionError(
                    f"Connection failed after {attempt + 1} attempts"
                ) from e

            except httpx.HTTPStatusError as e:
                raise ProofyHTTPError(
                    f"HTTP {e.response.status_code} error",
                    status_code=e.response.status_code,
                    response_text=e.response.text,
                ) from e

        # Should not reach here, but handle gracefully
        if last_exception:
            raise ProofyConnectionError(
                f"Request failed after {attempt} attempts"
            ) from last_exception
        raise ProofyConnectionError("Request failed")

    # ============================= API Methods =============================

    async def health(self) -> str:
        """Check service health; returns the response text (expected: "ok")."""
        response = await self._request("GET", "/health")
        return response.text

    # ============================= Runs =============================

    async def create_run(
        self,
        *,
        project_id: int,
        name: str,
        started_at: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a run (POST /v1/runs) and return JSON."""
        data: dict[str, Any] = {
            "project_id": int(project_id),
            "name": name,
        }
        if started_at is not None:
            data["started_at"] = started_at
        if attributes:
            data["attributes"] = ClientHelpers.stringify_attributes(attributes)

        response = await self._request("POST", "/v1/runs", json_body=data)
        return cast(dict[str, Any], response.json())

    async def update_run(
        self,
        run_id: int,
        *,
        name: str | None = None,
        status: RunStatus | int | None = None,
        ended_at: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        """Update a run (PATCH /v1/runs/{run_id}). Returns status code (expected 204)."""
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if status is not None:
            body["status"] = status
        if ended_at is not None:
            body["ended_at"] = ended_at
        if attributes:
            body["attributes"] = ClientHelpers.stringify_attributes(attributes)

        if ("status" in body) ^ ("ended_at" in body):
            raise ValueError("Both 'status' and 'ended_at' must be provided together.")
        if not body:
            raise ValueError("No fields to update were provided.")

        response = await self._request("PATCH", f"/v1/runs/{int(run_id)}", json_body=body)
        return response.status_code

    # ============================ Results ============================

    async def create_result(
        self,
        run_id: int,
        *,
        name: str,
        path: str,
        status: ResultStatus | int | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
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
            data["attributes"] = ClientHelpers.stringify_attributes(attributes)

        response = await self._request("POST", f"/v1/runs/{int(run_id)}/results", json_body=data)
        return cast(dict[str, Any], response.json())

    async def update_result(
        self,
        run_id: int,
        result_id: int,
        *,
        status: ResultStatus | int | None = None,
        ended_at: str | None = None,
        duration_ms: int | None = None,
        message: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        """Update a result (PATCH /v1/runs/{run_id}/results/{result_id}). Returns status code."""
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
            body["attributes"] = ClientHelpers.stringify_attributes(attributes)

        if not body:
            raise ValueError("No fields to update were provided.")
        if ("status" in body) and ("ended_at" not in body):
            raise ValueError("Setting a terminal 'status' requires 'ended_at'.")

        response = await self._request(
            "PATCH", f"/v1/runs/{int(run_id)}/results/{int(result_id)}", json_body=body
        )
        return response.status_code

    # ============================ Artifacts ===========================

    async def presign_artifact(
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
        response = await self._request(
            "POST",
            f"/v1/runs/{int(run_id)}/results/{int(result_id)}/artifacts/presign",
            json_body=data,
        )
        return cast(dict[str, Any], response.json())

    async def finalize_artifact(
        self, run_id: int, result_id: int, artifact_id: int
    ) -> tuple[int, dict[str, Any]]:
        """Finalize an artifact. Returns (status_code, json_or_empty_dict)."""
        response = await self._request(
            "POST",
            f"/v1/runs/{int(run_id)}/results/{int(result_id)}/artifacts/{int(artifact_id)}/finalize",
        )
        try:
            return response.status_code, cast(dict[str, Any], response.json())
        except ValueError:
            return response.status_code, {}

    async def upload_to_presigned_url(
        self,
        url: str,
        data: bytes | Path,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Upload data to a presigned URL (typically PUT).

        Args:
            url: Presigned URL
            data: File path or bytes
            headers: Optional headers (typically provided by presign response)

        Returns:
            httpx.Response
        """
        # For S3 presigned URLs, we MUST NOT include default client headers
        # (Authorization, User-Agent, Accept) as they weren't part of the signature.
        # We need to create a standalone request without the client's default headers.
        # We'll use a temporary async client with no default headers for this upload.

        async with httpx.AsyncClient(timeout=self.config.timeout) as upload_client:
            if isinstance(data, Path):
                with data.open("rb") as f:
                    content = f.read()
                return await upload_client.put(url, content=content, headers=headers or {})
            else:
                # Bytes
                return await upload_client.put(url, content=data, headers=headers or {})

    async def upload_artifact(
        self,
        run_id: int,
        result_id: int,
        *,
        file: str | Path | bytes | bytearray | memoryview,
        filename: str | None = None,
        mime_type: str | None = None,
        type: ArtifactType | int = ArtifactType.OTHER,
    ) -> dict[str, Any]:
        """Upload an artifact by auto-computing size, MIME type, and SHA-256.

        Args:
            run_id: Run ID
            result_id: Result ID
            file: Path or bytes-like (streams not supported in async for simplicity)
            filename: Optional filename (required if file is not a path)
            mime_type: Optional MIME type (auto-detected if omitted)
            type: Artifact type enum or int

        Returns:
            Dict with artifact_id, status_code, and finalize response
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
            size_bytes, digest = ClientHelpers.compute_file_hash(path)
            source_for_upload: Any = path
        elif isinstance(file, bytes | bytearray | memoryview):
            size_bytes, digest = ClientHelpers.compute_bytes_hash(file)
            source_for_upload = bytes(file)
        else:
            raise ValueError("Async client only supports Path or bytes-like objects")

        return await self.upload_artifact_file(
            run_id,
            result_id,
            file=source_for_upload,
            filename=final_filename,
            mime_type=final_mime,
            size_bytes=size_bytes,
            hash_sha256=digest,
            type=type,
        )

    async def upload_artifact_file(
        self,
        run_id: int,
        result_id: int,
        *,
        file: str | Path | bytes | bytearray | memoryview,
        filename: str,
        mime_type: str,
        size_bytes: int,
        hash_sha256: str,
        type: ArtifactType | int = ArtifactType.OTHER,
    ) -> dict[str, Any]:
        """Upload an artifact with known metadata: presign, upload, finalize.

        Args:
            run_id: Run ID
            result_id: Result ID
            file: Path or bytes-like
            filename: Filename
            mime_type: MIME type
            size_bytes: File size in bytes
            hash_sha256: SHA-256 hex digest
            type: Artifact type

        Returns:
            Dict with artifact_id, status_code, and finalize response
        """
        # Step 1: Presign
        presign = await self.presign_artifact(
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
        headers = cast(dict[str, str], upload_info.get("headers", {}))

        if method != "PUT" or not url:
            raise ValueError("Invalid presign response: missing PUT upload URL.")

        # Step 2: Upload to presigned URL
        if isinstance(file, bytes | bytearray | memoryview):
            put_resp = await self.upload_to_presigned_url(url, bytes(file), headers)
        elif isinstance(file, str | Path):
            put_resp = await self.upload_to_presigned_url(url, Path(file), headers)
        else:
            raise ValueError("Async client only supports Path or bytes-like objects")

        put_resp.raise_for_status()

        # Step 3: Finalize
        artifact_id = cast(int, presign.get("artifact_id"))
        status_code, finalize_json = await self.finalize_artifact(run_id, result_id, artifact_id)

        return {
            "artifact_id": artifact_id,
            "status_code": status_code,
            "finalize": finalize_json,
        }


__all__ = ["AsyncClient", "AsyncRetryConfig"]
