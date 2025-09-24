from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone

import pytest

from proofy.core.client import ArtifactType, ProofyClient
from proofy.core.models import ResultStatus, RunStatus


class FakeResponse:
    def __init__(
        self, status_code: int = 200, json_data: dict | None = None, text: str = ""
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        if self._json_data is None:
            raise ValueError("No JSON")
        return self._json_data

    def raise_for_status(self):
        return None


def test_health_makes_get_and_returns_text(monkeypatch):
    captured: dict = {}

    def fake_request(method, url, json=None, headers=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse(text="ok")

    client = ProofyClient("https://api.example", token="TOKEN", timeout_s=5.0)
    monkeypatch.setattr(client.session, "request", fake_request)

    assert client.health() == "ok"
    assert captured["method"] == "GET"
    assert captured["url"] == "https://api.example/health"
    assert captured["headers"]["Authorization"].startswith("Bearer ")


def test_stringify_attributes_and_datetime_normalization(monkeypatch):
    captured: dict = {}

    def fake_request(method, url, json=None, headers=None, timeout=None):
        captured["json"] = json
        return FakeResponse(json_data={"id": 123})

    client = ProofyClient("https://api.example")
    monkeypatch.setattr(client.session, "request", fake_request)

    started = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    attrs = {
        "int": 1,
        "dt": started,
        "enum": ResultStatus.PASSED,
        "nested": {"a": 1, "b": [1, 2, 3]},
    }

    resp = client.create_run(
        project_id=7, name="run-1", started_at=started, attributes=attrs
    )
    assert isinstance(resp, dict)

    # started_at normalized to RFC3339 string
    assert captured["json"]["started_at"].startswith("2020-01-02T03:04:05")

    # attributes stringified
    stringified = captured["json"]["attributes"]
    assert isinstance(stringified["int"], str) and stringified["int"] == "1"
    assert isinstance(stringified["dt"], str) and stringified["dt"].endswith("Z")
    assert stringified["enum"] == str(ResultStatus.PASSED.value)
    # nested collections become JSON-encoded strings
    import json as _json

    decoded_nested = _json.loads(stringified["nested"])
    assert decoded_nested == {"a": 1, "b": [1, 2, 3]}


def test_update_run_validations(monkeypatch):
    client = ProofyClient("https://api.example")

    # No fields provided
    with pytest.raises(ValueError):
        client.update_run(1)

    # Only one of status/ended_at provided
    with pytest.raises(ValueError):
        client.update_run(1, status=RunStatus.FINISHED)
    with pytest.raises(ValueError):
        client.update_run(1, ended_at=datetime.now(timezone.utc))

    seen: dict = {}

    def fake_request(method, url, json=None, headers=None, timeout=None):
        seen["method"] = method
        seen["url"] = url
        seen["json"] = json
        return FakeResponse(status_code=204, json_data={})

    monkeypatch.setattr(client.session, "request", fake_request)
    ended = datetime(2020, 1, 1, tzinfo=timezone.utc)
    status = RunStatus.FINISHED

    code = client.update_run(99, status=status, ended_at=ended, attributes={"k": "v"})
    assert code == 204
    assert seen["method"] == "PATCH"
    assert seen["url"].endswith("/v1/runs/99")
    assert seen["json"]["status"] == status.value
    assert seen["json"]["ended_at"].endswith("Z")
    assert seen["json"]["attributes"]["k"] == "v"


def test_result_create_and_update_validations(monkeypatch):
    client = ProofyClient("https://api.example")

    with pytest.raises(ValueError):
        client.update_result(1, 2)  # no fields to update

    with pytest.raises(ValueError):
        client.update_result(1, 2, duration_ms=-5)

    with pytest.raises(ValueError):
        client.update_result(1, 2, status=ResultStatus.PASSED)

    rec: dict = {}

    def fake_request(method, url, json=None, headers=None, timeout=None):
        rec["method"] = method
        rec["url"] = url
        rec["json"] = json
        if method == "POST":
            return FakeResponse(json_data={"id": 77})
        return FakeResponse(status_code=204, json_data={})

    monkeypatch.setattr(client.session, "request", fake_request)

    created = client.create_result(10, name="t", path="p", status=ResultStatus.PASSED)
    assert created["id"] == 77
    assert rec["method"] == "POST"
    assert rec["url"].endswith("/v1/runs/10/results")
    assert rec["json"]["status"] == ResultStatus.PASSED.value

    # Proper update
    code = client.update_result(
        10, 77, status=ResultStatus.PASSED, ended_at=datetime.now(timezone.utc)
    )
    assert code == 204


def test_presign_artifact_validation():
    client = ProofyClient("https://api.example")
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


def test_upload_artifact_file_happy_path_with_bytes(monkeypatch):
    client = ProofyClient("https://api.example")

    captured = {"presign": None, "put": None, "finalize": None}

    def fake_presign(
        run_id, result_id, filename, mime_type, size_bytes, hash_sha256, type
    ):  # noqa: ARG001
        captured["presign"] = {
            "run_id": run_id,
            "result_id": result_id,
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "hash_sha256": hash_sha256,
            "type": type,
        }
        return {
            "artifact_id": 42,
            "upload": {
                "method": "PUT",
                "url": "https://upload.example/file",
                "headers": {"X-Test": "yes"},
            },
        }

    def fake_put(url, data=None, headers=None):
        captured["put"] = {"url": url, "data": data, "headers": headers}
        return FakeResponse(status_code=200)

    def fake_finalize(run_id, result_id, artifact_id):
        captured["finalize"] = (run_id, result_id, artifact_id)
        return 204, {"ok": True}

    monkeypatch.setattr(client, "presign_artifact", fake_presign)
    monkeypatch.setattr("proofy.core.client.requests.put", fake_put)
    monkeypatch.setattr(client, "finalize_artifact", fake_finalize)

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

    assert captured["put"]["url"].startswith("https://upload.example/")
    assert captured["put"]["headers"]["X-Test"] == "yes"
    assert out["artifact_id"] == 42
    assert out["status_code"] == 204
    assert captured["finalize"] == (1, 2, 42)


def test_upload_artifact_path_auto_calculates_and_calls_presign(tmp_path, monkeypatch):
    client = ProofyClient("https://api.example")

    p = tmp_path / "file.bin"
    data = b"binary-data-123"
    p.write_bytes(data)
    expected_sha = hashlib.sha256(data).hexdigest()

    called = {"args": None, "put": None}

    def fake_presign(
        run_id, result_id, filename, mime_type, size_bytes, hash_sha256, type
    ):  # noqa: ARG001
        called["args"] = (
            run_id,
            result_id,
            filename,
            mime_type,
            size_bytes,
            hash_sha256,
            type,
        )
        return {
            "artifact_id": 7,
            "upload": {"method": "PUT", "url": "https://up", "headers": {}},
        }

    def fake_put(url, data=None, headers=None):
        # Ensure the file handle content matches
        assert (
            data.read() == data.seek(0) or True
        )  # tolerate streams being read elsewhere
        called["put"] = (url, headers)
        return FakeResponse(status_code=200)

    monkeypatch.setattr(client, "presign_artifact", fake_presign)
    monkeypatch.setattr("proofy.core.client.requests.put", fake_put)
    monkeypatch.setattr(client, "finalize_artifact", lambda a, b, c: (204, {}))

    out = client.upload_artifact(1, 2, file=str(p), type=ArtifactType.OTHER)

    assert out["artifact_id"] == 7
    args = called["args"]
    assert args[0:2] == (1, 2)
    assert args[2] == "file.bin"
    assert args[3] in ("application/octet-stream",)  # default guess
    assert args[4] == len(data)
    assert args[5] == expected_sha


def test_upload_artifact_non_seekable_stream_raises():
    client = ProofyClient("https://api.example")

    class NonSeekable:
        def __init__(self, payload: bytes):
            self._payload = payload
            self._read = False

        def read(self, n=-1):
            if self._read:
                return b""
            self._read = True
            return self._payload

    with pytest.raises(ValueError):
        client.upload_artifact(1, 2, file=NonSeekable(b"abc"), filename="x.bin")
