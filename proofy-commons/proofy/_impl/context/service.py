"""Context service orchestrating session/test lifecycle and ENV safety."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from ...core.models import TestResult
from ...export.attachments import cache_attachment, should_cache_for_mode
from ...hooks.manager import get_plugin_manager
from .backend import ContextBackend, ThreadLocalBackend
from .models import SessionContext


class ContextService:
    """High-level API for managing session/test contexts."""

    def __init__(self, backend: ContextBackend | None = None) -> None:
        self.backend = backend or ThreadLocalBackend()

    @property
    def test_ctx(self) -> TestResult | None:
        return self.backend.get_test()

    @property
    def session_ctx(self) -> SessionContext | None:
        return self.backend.get_session()

    def get_results(self) -> dict[str, TestResult]:
        return self.session_ctx.test_results if self.session_ctx else {}

    def get_result(self, id: str) -> TestResult | None:
        return self.get_results().get(id)

    # Session lifecycle
    def start_session(
        self, run_id: int | None = None, config: dict[str, Any] | None = None
    ) -> SessionContext:
        session = SessionContext(session_id=str(uuid.uuid4()), run_id=run_id, config=config)
        self.backend.set_session(session)
        return session

    def end_session(self) -> None:
        self.backend.set_session(None)

    # Test lifecycle
    def start_test(self, result: TestResult) -> TestResult:
        session = self.session_ctx
        self.backend.set_test(result)
        if session is not None:
            session.test_results[result.id] = result
        # signal start
        pm = get_plugin_manager()
        pm.hook.proofy_test_start(
            test_id=result.id,
            test_name=result.name or result.id,
            test_path=result.path,
        )
        return result

    def current_test(self) -> TestResult | None:
        return self.test_ctx

    def finish_test(self, result: TestResult) -> TestResult | None:
        session = self.session_ctx
        if session is not None:
            session.test_results[result.id] = result
        # signal finish via hooks carrying a simplified dict for now
        pm = get_plugin_manager()
        pm.hook.proofy_test_finish(test_result=result)
        # clear current test
        self.backend.set_test(None)
        return result

    # Metadata
    def set_name(self, name: str) -> None:
        if ctx := self.test_ctx:
            ctx.name = name

    def set_attribute(self, key: str, value: Any) -> None:
        if ctx := self.test_ctx:
            ctx.attributes[key] = value

    def add_attributes(self, **kwargs: Any) -> None:
        if ctx := self.test_ctx:
            ctx.attributes.update(kwargs)

    def add_tag(self, tag: str) -> None:
        if ctx := self.test_ctx:
            if tag not in ctx.tags:
                ctx.tags.append(tag)

    def add_tags(self, tags: list[str]) -> None:
        if ctx := self.test_ctx:
            new_tags = [t for t in tags if t not in ctx.tags]
            if new_tags:
                ctx.tags.extend(new_tags)

    # Attachments
    def attach(
        self,
        file: str | Path,
        *,
        name: str,
        mime_type: str | None = None,
        extension: str | None = None,
    ) -> None:
        ctx = self.test_ctx
        if not ctx:
            return
        original_path = Path(file)
        original_path_string = str(file) if isinstance(file, Path) else file
        path_to_store = original_path
        try:
            mode = os.getenv("PROOFY_MODE")
            if should_cache_for_mode(mode):
                path_to_store = cache_attachment(original_path)
        except Exception:
            path_to_store = original_path

        ctx.attachments.append(
            {
                "name": name,
                "path": str(path_to_store),
                "original_path": original_path_string,
                "mime_type": mime_type,
                "extension": extension,
            }
        )
