from __future__ import annotations

import io
from pathlib import Path

import proofy as api
import pytest
from proofy._internal.context.backend import ThreadLocalBackend
from proofy._internal.context.service import ContextService
from proofy.core.models import Severity, TestResult


@pytest.fixture(autouse=True)
def _fresh_service(monkeypatch):
    service = ContextService(ThreadLocalBackend())
    monkeypatch.setattr("proofy._internal.context.service.ContextService", ContextService)
    monkeypatch.setattr("proofy._internal.context.get_context_service", lambda: service)
    # Rebind module-level reference in api
    monkeypatch.setattr("proofy.core.api._context_service", service, raising=False)
    yield service


def make_result(id_: str = "t1") -> TestResult:
    return TestResult(
        id=id_, name="name", path="path", test_path="/tmp/test.py", test_identifier="abc123456789"
    )


def test_metadata_conveniences_and_getters(_fresh_service: ContextService):
    svc = _fresh_service
    svc.start_session(run_id=42, config={})
    tr = make_result("id-1")
    svc.start_test(tr)

    api.set_name("n1")
    api.set_description("desc")
    api.set_severity(Severity.CRITICAL)
    api.add_attributes(a=1)
    assert tr.name == "n1"
    assert tr.attributes["a"] == 1
    assert tr.attributes["__proofy_description"] == "desc"
    assert tr.attributes["__proofy_severity"] == "critical"
    assert api.get_current_test_id() == "id-1"

    # run getters
    assert api.get_current_run_id() == 42


def test_add_attachment_variants(tmp_path, _fresh_service: ContextService):
    svc = _fresh_service
    svc.start_session()
    tr = make_result("id-2")
    svc.start_test(tr)

    # path
    p = tmp_path / "a.txt"
    p.write_text("hello")
    api.add_attachment(str(p), name="p", mime_type="text/plain", extension="txt")

    # bytes
    api.add_attachment(Path(p), name="pp", mime_type="text/plain", extension="txt")
    api.add_attachment(b"bin", name="b", extension="bin")
    api.add_attachment(io.BytesIO(b"stream"), name="s", extension="bin")  # type: ignore[arg-type]

    assert [a.name for a in tr.attachments] == ["p", "pp", "b", "s"]
