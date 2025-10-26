"""Base configuration and utilities for Proofy HTTP clients."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal, cast

import httpx

from ..utils import format_datetime_rfc3339

logger = logging.getLogger("ProofyClient")


class RetryConfig:
    """Configuration for retry logic (shared between sync and async clients)."""

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
        import random

        delay = min(self.base_delay * (self.exponential_base**attempt), self.max_delay)
        if self.jitter:
            delay = random.uniform(0, delay)
        return delay


def should_retry(response: httpx.Response | None, exception: Exception | None) -> bool:
    """Determine if a request should be retried based on response or exception."""
    if exception:
        # Retry on timeout and connection errors
        return isinstance(exception, httpx.TimeoutException | httpx.ConnectError | httpx.ReadError)

    # Retry on 429 (rate limit) and 5xx server errors
    return bool(response and (response.status_code == 429 or 500 <= response.status_code < 600))


def get_retry_after(response: httpx.Response) -> float | None:
    """Extract Retry-After header value in seconds."""
    retry_after = response.headers.get("Retry-After")
    if not retry_after:
        return None

    try:
        # Try parsing as seconds
        return float(retry_after)
    except ValueError:
        # Could be HTTP date format, skip for simplicity
        return None


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


class ProofyClientError(Exception):
    """Base exception for Proofy client errors."""

    pass


class ProofyHTTPError(ProofyClientError):
    """HTTP error from the Proofy API."""

    def __init__(self, message: str, status_code: int, response_text: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class ProofyTimeoutError(ProofyClientError):
    """Request timeout error."""

    pass


class ProofyConnectionError(ProofyClientError):
    """Connection error."""

    pass


def _default_timeout() -> httpx.Timeout:
    """Create default timeout configuration."""
    return httpx.Timeout(connect=5.0, read=60.0, write=60.0, pool=60.0)


@dataclass(frozen=True)
class ClientConfig:
    """Shared configuration for HTTP clients."""

    base_url: str
    token: str | None = None
    timeout: httpx.Timeout | None = None
    max_keepalive: int = 20
    max_connections: int = 100
    http2: bool = False  # Disabled by default (requires h2 package for http2=True)
    user_agent: str = "proofy-python-0.1.0/httpx"
    max_retries: int = 3
    retry_delay: float = 1.0

    def __post_init__(self) -> None:
        """Set default timeout if not provided."""
        if self.timeout is None:
            object.__setattr__(self, "timeout", _default_timeout())

    @property
    def headers(self) -> dict[str, str]:
        """Build default headers."""
        headers = {
            "Accept": "*/*",
            "User-Agent": self.user_agent,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers


class ClientHelpers:
    """Shared helper methods for client implementations."""

    @staticmethod
    def normalize(value: Any) -> Any:
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
            return {k: ClientHelpers.normalize(v) for k, v in value.items()}
        if isinstance(value, list | tuple):
            return [ClientHelpers.normalize(v) for v in value]
        return value

    @staticmethod
    def stringify_attributes(attributes: dict[str, Any]) -> dict[str, str]:
        """Coerce attribute keys and values to strings, JSON-encoding complex values.

        - Keys are converted using str()
        - Values:
          - str → unchanged
          - dict/list/tuple/set → json.dumps(..., default=str)
          - other → str(value)
        Datetimes, Enums, Paths inside values are normalized first.
        """
        normalized = ClientHelpers.normalize(attributes)
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

    @staticmethod
    def build_url(base_url: str, path: str) -> str:
        """Build full URL from base and path."""
        base = base_url.rstrip("/")
        return f"{base}{path}" if path.startswith("/") else f"{base}/{path}"

    @staticmethod
    def handle_http_error(response: httpx.Response) -> None:
        """Convert httpx errors to Proofy errors."""
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ProofyHTTPError(
                f"HTTP {response.status_code} error",
                status_code=response.status_code,
                response_text=response.text,
            ) from e

    @staticmethod
    def compute_file_hash(file_path: Path, chunk_size: int = 1024 * 1024) -> tuple[int, str]:
        """Compute size and SHA-256 hash for a file.

        Args:
            file_path: Path to the file
            chunk_size: Size of chunks to read (default 1MB)

        Returns:
            Tuple of (size_bytes, sha256_hex_digest)
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        size_bytes = int(file_path.stat().st_size)
        sha256 = hashlib.sha256()

        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                sha256.update(chunk)

        return size_bytes, sha256.hexdigest()

    @staticmethod
    def compute_bytes_hash(data: bytes | bytearray | memoryview) -> tuple[int, str]:
        """Compute size and SHA-256 hash for bytes-like data.

        Args:
            data: Bytes-like data

        Returns:
            Tuple of (size_bytes, sha256_hex_digest)
        """
        buf = bytes(data)
        return len(buf), hashlib.sha256(buf).hexdigest()


__all__ = [
    "ArtifactType",
    "ClientConfig",
    "ClientHelpers",
    "PresignUpload",
    "ProofyClientError",
    "ProofyConnectionError",
    "ProofyHTTPError",
    "ProofyTimeoutError",
    "RetryConfig",
    "should_retry",
    "get_retry_after",
]
