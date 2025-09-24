from __future__ import annotations

import io
from pathlib import Path

import pytest
from proofy._impl.context.backend import ThreadLocalBackend
from proofy._impl.context.service import ContextService
from proofy._impl.hooks.manager import get_plugin_manager, reset_plugin_manager
from proofy._impl.hooks.specs import hookimpl
from proofy.core.models import TestResult


@pytest.fixture(autouse=True)
def reset_pm():
    reset_plugin_manager()
    yield
    reset_plugin_manager()


def make_result(id: str = "t1") -> TestResult:
    return TestResult(id=id, name="name", path="path", test_path="/tmp/test.py")


def test_session_and_test_lifecycle_and_hooks(monkeypatch):
    cs = ContextService(ThreadLocalBackend())

    # start session
    sess = cs.start_session(run_id=123, config={"a": 1})
    assert sess.run_id == 123
    assert cs.session_ctx is sess
    assert cs.get_results() == {}

    # hook spy
    calls: list[tuple[str, tuple, dict]] = []

    class Plugin:
        @hookimpl
        def proofy_test_start(self, test_id: str, test_name: str, test_path: str, metadata=None):  # noqa: ANN001
            calls.append(
                (
                    "start",
                    (),
                    {
                        "test_id": test_id,
                        "test_name": test_name,
                        "test_path": test_path,
                        "metadata": metadata,
                    },
                )
            )

        @hookimpl
        def proofy_test_finish(self, test_result):  # noqa: ANN001
            calls.append(("finish", (test_result,), {}))

    pm = get_plugin_manager()
    pm.register(Plugin())

    # start test
    tr = make_result("id-1")
    cs.start_test(tr)
    assert cs.current_test() is tr
    assert cs.get_result("id-1") is tr
    assert len(calls) == 1 and calls[0][0] == "start"
    assert calls[0][2]["test_id"] == "id-1"
    assert calls[0][2]["test_path"] == "path"

    # metadata updates
    cs.set_name("new-name")
    cs.set_attribute("k", "v")
    cs.add_attributes(x=1, y=2)
    cs.add_tag("tag1")
    cs.add_tags(["tag1", "tag2"])  # ensure dedupe
    assert tr.name == "new-name"
    assert tr.attributes["k"] == "v"
    assert tr.attributes["x"] == 1 and tr.attributes["y"] == 2
    assert tr.tags == ["tag1", "tag2"]

    # finish test clears current
    cs.finish_test(tr)
    assert cs.current_test() is None
    assert len(calls) == 2 and calls[1][0] == "finish"
    assert calls[1][1][0] is tr

    # end session clears session
    cs.end_session()
    assert cs.session_ctx is None


def test_attach_from_path_uses_cache_when_enabled(tmp_path, monkeypatch):
    cs = ContextService(ThreadLocalBackend())
    cs.start_session()
    tr = make_result("id-2")
    cs.start_test(tr)

    # prepare source file
    src = tmp_path / "note.txt"
    src.write_text("hello")

    # force caching on
    monkeypatch.setenv("PROOFY_DISABLE_ATTACHMENT_CACHE", "false")
    monkeypatch.setenv("PROOFY_TEMP_DIR", str(tmp_path))

    cs.attach(str(src), name="n", mime_type="text/plain", extension="txt")
    assert len(tr.attachments) == 1
    att = tr.attachments[0]
    assert att.name == "n"
    # path should be inside cache dir, not original
    assert Path(att.path).exists()
    assert att.original_path == str(src)
    # size and sha are computed by cache step
    assert att.size_bytes == 5
    assert isinstance(att.sha256, str) and len(att.sha256) == 64


def test_attach_bytes_cached_and_metadata_set(tmp_path, monkeypatch):
    cs = ContextService(ThreadLocalBackend())
    cs.start_session()
    tr = make_result("id-3")
    cs.start_test(tr)

    monkeypatch.setenv("PROOFY_TEMP_DIR", str(tmp_path))
    cs.attach(b"data", name="bin", extension="bin")

    att = tr.attachments[0]
    assert att.original_path == "<bytes>"
    assert Path(att.path).exists()
    assert att.size_bytes == 4
    assert isinstance(att.sha256, str) and len(att.sha256) == 64


def test_attach_stream_cached(tmp_path, monkeypatch):
    cs = ContextService(ThreadLocalBackend())
    cs.start_session()
    tr = make_result("id-4")
    cs.start_test(tr)

    monkeypatch.setenv("PROOFY_TEMP_DIR", str(tmp_path))
    stream = io.BytesIO(b"stream-data")
    cs.attach(stream, name="s", extension="bin")

    att = tr.attachments[0]
    assert att.original_path == "<stream>"
    assert Path(att.path).exists()
    assert att.size_bytes == len(b"stream-data")


def test_attach_path_no_cache_in_live_mode_when_cache_disabled(tmp_path, monkeypatch):
    cs = ContextService(ThreadLocalBackend())
    cs.start_session()
    tr = make_result("id-5")
    cs.start_test(tr)

    src = tmp_path / "f.bin"
    src.write_bytes(b"abc")

    monkeypatch.setenv("PROOFY_OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("PROOFY_TEMP_DIR", str(tmp_path))
    monkeypatch.setenv("PROOFY_DISABLE_ATTACHMENT_CACHE", "true")
    monkeypatch.setenv("PROOFY_MODE", "live")

    cs.attach(str(src), name="live")

    att = tr.attachments[0]
    # When cache disabled in live mode, path should remain original (no cache copy)
    assert att.path == str(src)
    assert att.size_bytes is None and att.sha256 is None
