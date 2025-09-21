from __future__ import annotations

import os
from pathlib import Path

from proofy._impl.context.service import ContextService


class TestContextServiceBasics:
    def test_session_and_test_lifecycle(self) -> None:
        svc = ContextService()

        # Start session
        session = svc.start_session(run_id=123, config={"mode": "lazy"})
        assert session.run_id == 123

        # Start test
        ctx = svc.start_test("nodeid::test_example", name="Example")
        assert ctx.test_id == "nodeid::test_example"
        assert ctx.name == "Example"
        assert ctx.started_at is not None

        # Current test exists
        cur = svc.current_test()
        assert cur is not None

        # Finish test clears current
        svc.finish_test(outcome="passed")
        assert svc.current_test() is None

        # End session clears it
        svc.end_session()


class TestContextServiceEnv:
    def test_env_is_restored(self, monkeypatch) -> None:
        svc = ContextService()
        svc.start_session()
        svc.start_test("t1")

        # Ensure key not set initially
        monkeypatch.delenv("CTX_SVC_KEY", raising=False)

        # Set env and unset via service
        svc.set_env("CTX_SVC_KEY", "value")
        assert os.environ.get("CTX_SVC_KEY") == "value"

        svc.unset_env("CTX_SVC_KEY")
        assert "CTX_SVC_KEY" not in os.environ

        # Restore on finish should keep it unset (original was None)
        svc.finish_test(outcome="passed")
        assert "CTX_SVC_KEY" not in os.environ

    def test_env_restores_original_value(self, monkeypatch) -> None:
        svc = ContextService()
        svc.start_session()
        svc.start_test("t2")

        # Original value present
        monkeypatch.setenv("CTX_SVC_ORIG", "orig")

        # Change during test
        svc.set_env("CTX_SVC_ORIG", "modified")
        assert os.environ.get("CTX_SVC_ORIG") == "modified"

        # On finish it should restore original
        svc.finish_test(outcome="passed")
        assert os.environ.get("CTX_SVC_ORIG") == "orig"


class TestContextServiceAttachments:
    def test_add_attachment_records_metadata(self, tmp_path: Path) -> None:
        svc = ContextService()
        svc.start_session()
        svc.start_test("t3")

        f = tmp_path / "file.txt"
        f.write_text("hello")

        svc.attach(f, name="log", mime_type="text/plain")

        ctx = svc.current_test()
        assert ctx is not None
        assert len(ctx.attachments) == 1
        a = ctx.attachments[0]
        assert a["name"] == "log"
        assert Path(a["path"]).exists()
