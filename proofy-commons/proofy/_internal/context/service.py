"""Context service orchestrating session/test lifecycle and ENV safety."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import IO, Any

from ..._internal.config import ProofyConfig
from ..._internal.hooks import get_plugin_manager
from ...core.client import ArtifactType
from ...core.models import Attachment, Severity, TestResult
from ..artifacts import (
    cache_attachment,
    cache_attachment_from_bytes,
    cache_attachment_from_stream,
    is_cached_path,
    should_cache_for_mode,
)
from ..constants import PredefinedAttribute
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

    def get_run_name(self) -> str | None:
        return self.session_ctx.run_name if self.session_ctx else None

    def get_run_id(self) -> int | None:
        return self.session_ctx.run_id if self.session_ctx else None

    # Session lifecycle
    def start_session(
        self,
        run_id: int | None = None,
        config: ProofyConfig | None = None,
        run_name: str | None = None,
        run_attributes: dict[str, Any] | None = None,
    ) -> SessionContext:
        session = SessionContext(
            session_id=str(uuid.uuid4()),
            run_id=run_id,
            config=config,
            run_name=run_name,
            run_attributes=run_attributes or {},
        )
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

    def set_description(self, description: str) -> None:
        if ctx := self.test_ctx:
            ctx.attributes[PredefinedAttribute.DESCRIPTION.value] = description

    def set_severity(self, severity: Severity | str) -> None:
        if ctx := self.test_ctx:
            value = severity.value if isinstance(severity, Severity) else severity
            ctx.attributes[PredefinedAttribute.SEVERITY.value] = value

    def add_tag(self, tag: str) -> None:
        if (ctx := self.test_ctx) and tag not in ctx.tags:
            ctx.tags.append(tag)

    def add_tags(self, tags: list[str]) -> None:
        if ctx := self.test_ctx:
            new_tags = [t for t in tags if t not in ctx.tags]
            if new_tags:
                ctx.tags.extend(new_tags)

    # Run-level metadata
    def set_run_attribute(self, key: str, value: Any) -> None:
        if sess := self.session_ctx:
            sess.run_attributes[key] = value

    def add_run_attributes(self, **kwargs: Any) -> None:
        if sess := self.session_ctx:
            sess.run_attributes.update(kwargs)

    def get_run_attributes(self) -> dict[str, Any]:
        if sess := self.session_ctx:
            return sess.run_attributes.copy()
        return {}

    # Attachments
    def attach(
        self,
        file: str | Path | bytes | bytearray | IO[bytes],
        *,
        name: str,
        mime_type: str | None = None,
        extension: str | None = None,
        artifact_type: ArtifactType | int = ArtifactType.ATTACHMENT,
    ) -> None:
        ctx = self.test_ctx
        if not ctx:
            return
        # Normalize input: accept path-like or in-memory content
        path_to_store: Path
        original_path_string: str
        mode = os.getenv("PROOFY_MODE", "").lower()
        do_immediate = mode == "live"
        cached_size: int | None = None
        cached_sha: str | None = None

        if isinstance(file, str | Path):
            # Path-like: prefer zero-copy; in live mode consider immediate upload
            original_path = Path(file)
            original_path_string = str(file) if isinstance(file, Path) else file
            path_to_store = original_path
            # In live, if we already have run_id/result_id, we could upload immediately (optional)
            if do_immediate and self.test_ctx and self.test_ctx.run_id and self.test_ctx.result_id:
                try:
                    # Best effort mime guess if missing
                    eff_mime = mime_type
                    if eff_mime is None and extension:
                        import mimetypes as _m

                        eff_mime = _m.guess_type(f"f.{extension}")[0]
                    eff_mime = eff_mime or "application/octet-stream"
                    # Placeholder for potential immediate upload integration at this layer
                except Exception:
                    pass
        elif isinstance(file, bytes | bytearray):
            # Bytes: in lazy/batch write directly to cache; in live immediate upload is optional
            if do_immediate and self.test_ctx and self.test_ctx.run_id and self.test_ctx.result_id:
                # Avoid writing to disk; upload can occur immediately at test finish
                # Still record a cache path to keep a consistent structure
                suffix = f".{extension}" if extension else None
                path_to_store, cached_size, cached_sha = cache_attachment_from_bytes(
                    bytes(file), suffix=suffix
                )
                original_path_string = "<bytes>"
            else:
                suffix = f".{extension}" if extension else None
                path_to_store, cached_size, cached_sha = cache_attachment_from_bytes(
                    bytes(file), suffix=suffix
                )
                original_path_string = "<bytes>"
        else:
            # Stream: write directly to cache in a single pass
            suffix = f".{extension}" if extension else None
            path_to_store, cached_size, cached_sha = cache_attachment_from_stream(
                file, suffix=suffix
            )
            original_path_string = "<stream>"
        try:
            # For path inputs, copy to cache if required and not already cached
            if (
                should_cache_for_mode(mode)
                and isinstance(file, str | Path)
                and not is_cached_path(path_to_store)
            ):
                path_to_store, cached_size, cached_sha = cache_attachment(path_to_store)
        except Exception:
            pass

        ctx.attachments.append(
            Attachment(
                name=name,
                path=str(path_to_store),
                original_path=original_path_string,
                mime_type=mime_type,
                extension=extension,
                size_bytes=cached_size,
                sha256=cached_sha,
                artifact_type=int(artifact_type),
            )
        )
