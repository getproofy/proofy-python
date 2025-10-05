"""Unit tests for the httpx-based sync and async clients."""

from __future__ import annotations

import httpx
import pytest
import respx
from proofy.core.client import AsyncClient, Client
from proofy.core.client.base import ProofyHTTPError
from proofy.core.models import ResultStatus, RunStatus


class TestSyncClient:
    """Tests for the synchronous Client."""

    @respx.mock
    def test_health(self):
        """Test health check endpoint."""
        client = Client(base_url="https://api.example.com", token="test-token")

        route = respx.get("https://api.example.com/health").mock(
            return_value=httpx.Response(200, text="ok")
        )

        result = client.health()

        assert result == "ok"
        assert route.called

    @respx.mock
    def test_create_run(self):
        """Test creating a run."""
        client = Client(base_url="https://api.example.com", token="test-token")

        route = respx.post("https://api.example.com/v1/runs").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 123,
                    "project_id": 1,
                    "name": "Test Run",
                    "status": RunStatus.STARTED.value,
                },
            )
        )

        response = client.create_run(project_id=1, name="Test Run")

        assert response["id"] == 123
        assert response["name"] == "Test Run"
        assert route.called

    @respx.mock
    def test_create_result(self):
        """Test creating a test result."""
        client = Client(base_url="https://api.example.com", token="test-token")

        route = respx.post("https://api.example.com/v1/runs/123/results").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 456,
                    "name": "test_example",
                    "path": "tests/test_example.py::test_example",
                    "status": ResultStatus.PASSED.value,
                },
            )
        )

        response = client.create_result(
            run_id=123,
            name="test_example",
            path="tests/test_example.py::test_example",
            status=ResultStatus.PASSED,
        )

        assert response["id"] == 456
        assert response["name"] == "test_example"
        assert route.called

    @respx.mock
    def test_http_error(self):
        """Test that HTTP errors are properly raised."""
        client = Client(base_url="https://api.example.com", token="test-token")

        respx.get("https://api.example.com/health").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(ProofyHTTPError) as exc_info:
            client.health()

        assert exc_info.value.status_code == 500

    @respx.mock
    def test_retry_on_500(self):
        """Test that 500 errors trigger retries."""
        client = Client(base_url="https://api.example.com", token="test-token", max_retries=2)

        # First two calls fail, third succeeds
        route = respx.get("https://api.example.com/health")
        route.side_effect = [
            httpx.Response(500, text="Error"),
            httpx.Response(500, text="Error"),
            httpx.Response(200, text="ok"),
        ]

        result = client.health()

        assert result == "ok"
        assert route.call_count == 3

    @respx.mock
    def test_context_manager(self):
        """Test that client works as context manager."""
        with Client(base_url="https://api.example.com", token="test-token") as client:
            respx.get("https://api.example.com/health").mock(
                return_value=httpx.Response(200, text="ok")
            )
            result = client.health()
            assert result == "ok"


class TestAsyncClient:
    """Tests for the asynchronous AsyncClient."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_health(self):
        """Test health check endpoint."""
        client = AsyncClient(base_url="https://api.example.com", token="test-token")

        route = respx.get("https://api.example.com/health").mock(
            return_value=httpx.Response(200, text="ok")
        )

        result = await client.health()

        assert result == "ok"
        assert route.called

        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_run(self):
        """Test creating a run."""
        client = AsyncClient(base_url="https://api.example.com", token="test-token")

        route = respx.post("https://api.example.com/v1/runs").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 123,
                    "project_id": 1,
                    "name": "Test Run",
                    "status": RunStatus.STARTED.value,
                },
            )
        )

        response = await client.create_run(project_id=1, name="Test Run")

        assert response["id"] == 123
        assert response["name"] == "Test Run"
        assert route.called

        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_result(self):
        """Test creating a test result."""
        client = AsyncClient(base_url="https://api.example.com", token="test-token")

        route = respx.post("https://api.example.com/v1/runs/123/results").mock(
            return_value=httpx.Response(
                201,
                json={
                    "id": 456,
                    "name": "test_example",
                    "path": "tests/test_example.py::test_example",
                    "status": ResultStatus.PASSED.value,
                },
            )
        )

        response = await client.create_result(
            run_id=123,
            name="test_example",
            path="tests/test_example.py::test_example",
            status=ResultStatus.PASSED,
        )

        assert response["id"] == 456
        assert response["name"] == "test_example"
        assert route.called

        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_http_error(self):
        """Test that HTTP errors are properly raised."""
        client = AsyncClient(base_url="https://api.example.com", token="test-token")

        respx.get("https://api.example.com/health").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )

        with pytest.raises(ProofyHTTPError) as exc_info:
            await client.health()

        assert exc_info.value.status_code == 500

        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_retry_on_500(self):
        """Test that 500 errors trigger retries."""
        client = AsyncClient(base_url="https://api.example.com", token="test-token", max_retries=2)

        # First two calls fail, third succeeds
        route = respx.get("https://api.example.com/health")
        route.side_effect = [
            httpx.Response(500, text="Error"),
            httpx.Response(500, text="Error"),
            httpx.Response(200, text="ok"),
        ]

        result = await client.health()

        assert result == "ok"
        assert route.call_count == 3

        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_context_manager(self):
        """Test that client works as async context manager."""
        async with AsyncClient(base_url="https://api.example.com", token="test-token") as client:
            respx.get("https://api.example.com/health").mock(
                return_value=httpx.Response(200, text="ok")
            )
            result = await client.health()
            assert result == "ok"
