from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx
import pytest
import respx
from proofy.core.client import ArtifactType, Client
from proofy.core.models import ResultStatus, RunStatus


@respx.mock
def test_health_makes_get_and_returns_text():
    """Test health endpoint with proper authorization."""
    client = Client("https://api.example", token="TOKEN", timeout=5.0)

    route = respx.get("https://api.example/health").mock(
        return_value=httpx.Response(200, text="ok")
    )

    assert client.health() == "ok"
    assert route.called

    # Verify authorization header was sent
    request = route.calls.last.request
    assert "Authorization" in request.headers
    assert request.headers["Authorization"].startswith("Bearer ")


@respx.mock
def test_stringify_attributes_and_datetime_normalization():
    """Test that attributes are stringified and datetimes normalized."""
    client = Client("https://api.example")

    started = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    attrs = {
        "int": 1,
        "dt": started,
        "enum": ResultStatus.PASSED,
        "nested": {"a": 1, "b": [1, 2, 3]},
    }

    route = respx.post("https://api.example/v1/runs").mock(
        return_value=httpx.Response(201, json={"id": 123})
    )

    resp = client.create_run(project_id=7, name="run-1", started_at=started, attributes=attrs)
    assert isinstance(resp, dict)
    assert resp["id"] == 123

    # Check the request body
    request = route.calls.last.request
    import json

    body = json.loads(request.content)

    # started_at normalized to RFC3339 string
    assert body["started_at"].startswith("2020-01-02T03:04:05")

    # attributes stringified
    stringified = body["attributes"]
    assert isinstance(stringified["int"], str) and stringified["int"] == "1"
    assert isinstance(stringified["dt"], str) and stringified["dt"].endswith("Z")
    assert stringified["enum"] == str(ResultStatus.PASSED.value)
    # nested collections become JSON-encoded strings
    decoded_nested = json.loads(stringified["nested"])
    assert decoded_nested == {"a": 1, "b": [1, 2, 3]}


def test_update_run_validations():
    """Test update_run validation logic."""
    client = Client("https://api.example")

    # No fields provided
    with pytest.raises(ValueError):
        client.update_run(1)

    # Only one of status/ended_at provided
    with pytest.raises(ValueError):
        client.update_run(1, status=RunStatus.FINISHED)
    with pytest.raises(ValueError):
        client.update_run(1, ended_at=datetime.now(timezone.utc))


@respx.mock
def test_update_run_with_valid_fields():
    """Test update_run with valid fields."""
    client = Client("https://api.example")
    ended = datetime(2020, 1, 1, tzinfo=timezone.utc)
    status = RunStatus.FINISHED

    route = respx.patch("https://api.example/v1/runs/99").mock(return_value=httpx.Response(204))

    code = client.update_run(99, status=status, ended_at=ended, attributes={"k": "v"})
    assert code == 204

    # Check request
    request = route.calls.last.request
    import json

    body = json.loads(request.content)
    assert body["status"] == status.value
    assert body["ended_at"].endswith("Z")
    assert body["attributes"]["k"] == "v"


def test_result_create_and_update_validations():
    """Test result validation logic."""
    client = Client("https://api.example")

    with pytest.raises(ValueError):
        client.update_result(1, 2)  # no fields to update

    with pytest.raises(ValueError):
        client.update_result(1, 2, duration_ms=-5)

    with pytest.raises(ValueError):
        client.update_result(1, 2, status=ResultStatus.PASSED)


@respx.mock
def test_result_create_and_update():
    """Test result creation and updates."""
    client = Client("https://api.example")

    # Create result
    create_route = respx.post("https://api.example/v1/runs/10/results").mock(
        return_value=httpx.Response(201, json={"id": 77})
    )

    created = client.create_result(
        10, name="t", path="p", test_identifier="abc123", status=ResultStatus.PASSED
    )
    assert created["id"] == 77

    request = create_route.calls.last.request
    import json

    body = json.loads(request.content)
    assert body["status"] == ResultStatus.PASSED.value

    # Proper update
    respx.patch("https://api.example/v1/runs/10/results/77").mock(return_value=httpx.Response(204))

    code = client.update_result(
        10, 77, status=ResultStatus.PASSED, ended_at=datetime.now(timezone.utc)
    )
    assert code == 204


def test_presign_artifact_validation():
    """Test presign_artifact validation."""
    client = Client("https://api.example")
    with pytest.raises(ValueError):
        client.presign_artifact(
            1,
            2,
            filename="x.txt",
            mime_type="text/plain",
            size_bytes=0,
            hash_sha256="00",
            type=ArtifactType.OTHER,
        )


@respx.mock
def test_upload_artifact_file_happy_path_with_bytes():
    """Test upload_artifact_file with bytes."""
    client = Client("https://api.example")

    # Mock presign endpoint
    respx.post("https://api.example/v1/runs/1/results/2/artifacts/presign").mock(
        return_value=httpx.Response(
            200,
            json={
                "artifact_id": 42,
                "upload": {
                    "method": "PUT",
                    "url": "https://upload.example/file",
                    "headers": {"X-Test": "yes"},
                },
            },
        )
    )

    # Mock upload endpoint
    upload_route = respx.put("https://upload.example/file").mock(return_value=httpx.Response(200))

    # Mock finalize endpoint
    finalize_route = respx.post(
        "https://api.example/v1/runs/1/results/2/artifacts/42/finalize"
    ).mock(return_value=httpx.Response(204, json={"ok": True}))

    data = b"hello"
    sha = hashlib.sha256(data).hexdigest()
    out = client.upload_artifact_file(
        1,
        2,
        file=data,
        filename="hello.txt",
        mime_type="text/plain",
        size_bytes=len(data),
        hash_sha256=sha,
        type=ArtifactType.ATTACHMENT,
    )

    assert upload_route.called
    assert upload_route.calls.last.request.headers.get("X-Test") == "yes"
    assert out["artifact_id"] == 42
    assert out["status_code"] == 204
    assert finalize_route.called


@respx.mock
def test_upload_artifact_path_auto_calculates_and_calls_presign(tmp_path):
    """Test upload_artifact with file path."""
    client = Client("https://api.example")

    p = tmp_path / "file.bin"
    data = b"binary-data-123"
    p.write_bytes(data)
    expected_sha = hashlib.sha256(data).hexdigest()

    # Mock presign
    presign_route = respx.post("https://api.example/v1/runs/1/results/2/artifacts/presign").mock(
        return_value=httpx.Response(
            200,
            json={
                "artifact_id": 7,
                "upload": {"method": "PUT", "url": "https://up", "headers": {}},
            },
        )
    )

    # Mock upload
    respx.put("https://up").mock(return_value=httpx.Response(200))

    # Mock finalize
    respx.post("https://api.example/v1/runs/1/results/2/artifacts/7/finalize").mock(
        return_value=httpx.Response(204, json={})
    )

    out = client.upload_artifact(1, 2, file=str(p), type=ArtifactType.OTHER)

    assert out["artifact_id"] == 7
    assert presign_route.called

    # Check presign request
    import json

    body = json.loads(presign_route.calls.last.request.content)
    assert body["filename"] == "file.bin"
    assert body["mime_type"] in ("application/octet-stream",)  # default guess
    assert body["size_bytes"] == len(data)
    assert body["hash_sha256"] == expected_sha


def test_upload_artifact_non_seekable_stream_raises():
    """Test that non-seekable streams are handled properly."""
    client = Client("https://api.example")

    class NonSeekable:
        def __init__(self, payload: bytes):
            self._payload = payload
            self._read = False

        def read(self, n=-1):
            if self._read:
                return b""
            self._read = True
            return self._payload

    # Non-seekable streams should work now (we read them into memory)
    # Let's test that it raises ValueError with proper message
    with pytest.raises(ValueError, match="filename.*required"):
        client.upload_artifact(1, 2, file=NonSeekable(b"abc"))
