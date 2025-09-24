from __future__ import annotations

import io
from pathlib import Path

import pytest

import proofy as api
from proofy._impl.context.backend import ThreadLocalBackend
from proofy._impl.context.service import ContextService
from proofy._impl.context.models import SessionContext
from proofy.core.models import TestResult


@pytest.fixture(autouse=True)
def _fresh_service(monkeypatch):
    service = ContextService(ThreadLocalBackend())
    monkeypatch.setattr("proofy._impl.context.service.ContextService", ContextService)
    monkeypatch.setattr("proofy._impl.context.get_context_service", lambda: service)
    # Rebind module-level reference in api
    monkeypatch.setattr("proofy.core.api._context_service", service, raising=False)
    yield service


def make_result(id_: str = "t1") -> TestResult:
    return TestResult(id=id_, name="name", path="path", test_path="/tmp/test.py")


def test_metadata_conveniences_and_getters(_fresh_service: ContextService):
    svc = _fresh_service
    svc.start_session(run_id=42, config={})
    tr = make_result("id-1")
    svc.start_test(tr)

    api.set_name("n1")
    api.set_title("n2")
    api.set_description("desc")
    api.set_severity("critical")
    api.add_attributes(a=1)
    api.add_tag("x")
    api.add_tags(["x", "y"])  # dedupe behavior asserted in service tests

    assert tr.name == "n2"  # last set wins, title delegates to set_name
    assert tr.attributes["a"] == 1
    assert tr.attributes["__proofy_description"] == "desc"
    assert tr.attributes["__proofy_severity"] == "critical"
    assert tr.tags == ["x", "y"]
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
