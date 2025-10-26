"""Test fixtures for pytest-proofy test suite."""

from __future__ import annotations

import itertools
from typing import Any

import pytest

_run_id_counter = itertools.count(1000)
_result_id_counter = itertools.count(5000)


class _DummySyncClient:
    """Minimal stand-in for the Proofy synchronous client.

    It captures run/result creation requests without performing any network I/O.
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float | Any = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        **_: Any,
    ) -> None:
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    # Runs -----------------------------------------------------------------
    def create_run(
        self,
        *,
        project_id: int,
        name: str,
        started_at: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = next(_run_id_counter)
        return {
            "id": run_id,
            "project_id": project_id,
            "name": name,
            "started_at": started_at,
            "attributes": attributes or {},
        }

    def update_run(
        self,
        run_id: int,
        *,
        name: str | None = None,
        status: Any | None = None,
        ended_at: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        return 204

    # Results ---------------------------------------------------------------
    def create_result(
        self,
        run_id: int,
        *,
        name: str,
        path: str,
        test_identifier: str,
        status: Any | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        duration_ms: int | None = None,
        message: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result_id = next(_result_id_counter)
        return {
            "id": result_id,
            "run_id": run_id,
            "name": name,
            "path": path,
            "test_identifier": test_identifier,
            "status": status,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "message": message,
            "attributes": attributes or {},
        }

    def update_result(
        self,
        run_id: int,
        result_id: int,
        *,
        status: Any | None = None,
        ended_at: str | None = None,
        duration_ms: int | None = None,
        message: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        return 204


class _DummyAsyncClient:
    """Minimal async variant used by the background uploader worker."""

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 3,
        **_: Any,
    ) -> None:
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.max_retries = max_retries

    async def create_run(
        self,
        *,
        project_id: int,
        name: str,
        started_at: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = next(_run_id_counter)
        return {
            "id": run_id,
            "project_id": project_id,
            "name": name,
            "started_at": started_at,
            "attributes": attributes or {},
        }

    async def update_run(
        self,
        run_id: int,
        *,
        name: str | None = None,
        status: Any | None = None,
        ended_at: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        return 204

    async def create_result(
        self,
        run_id: int,
        *,
        name: str,
        path: str,
        test_identifier: str,
        status: Any | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        duration_ms: int | None = None,
        message: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": next(_result_id_counter),
            "run_id": run_id,
            "name": name,
            "path": path,
            "test_identifier": test_identifier,
            "status": status,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_ms": duration_ms,
            "message": message,
            "attributes": attributes or {},
        }

    async def update_result(
        self,
        run_id: int,
        result_id: int,
        *,
        status: Any | None = None,
        ended_at: str | None = None,
        duration_ms: int | None = None,
        message: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> int:
        return 204

    async def upload_artifact_file(
        self,
        *,
        run_id: int,
        result_id: int,
        file: Any,
        filename: str,
        mime_type: str,
        size_bytes: int,
        hash_sha256: str,
        type: Any,
    ) -> dict[str, Any]:
        return {
            "id": next(_result_id_counter),
            "run_id": run_id,
            "result_id": result_id,
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "hash_sha256": hash_sha256,
            "type": type,
        }

    async def close(self) -> None:  # pragma: no cover - nothing to clean up
        return None


@pytest.fixture(autouse=True)
def _reset_plugin_manager() -> None:
    """Reset plugin manager between tests to avoid registration conflicts."""
    from proofy._internal.hooks.manager import reset_plugin_manager

    reset_plugin_manager()
    yield
    reset_plugin_manager()


@pytest.fixture(autouse=True)
def _stub_proofy_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub synchronous and async Proofy clients for the entire test suite."""

    # Provide dummy credentials so the plugin considers the configuration valid.
    monkeypatch.setenv("PROOFY_TOKEN", "test-token")
    monkeypatch.setenv("PROOFY_PROJECT_ID", "12345")
    monkeypatch.setenv("PROOFY_API_BASE", "https://example.invalid")

    # Replace network clients with local dummies.
    monkeypatch.setattr(
        "proofy._internal.results.result_handler.Client",
        _DummySyncClient,
    )
    monkeypatch.setattr(
        "proofy._internal.uploader.worker.AsyncClient",
        _DummyAsyncClient,
    )
