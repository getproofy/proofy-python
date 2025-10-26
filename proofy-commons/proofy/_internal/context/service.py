"""Context service orchestrating session/test lifecycle and ENV safety."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import IO, Any

from ..._internal.config import ProofyConfig
from ..._internal.hooks import get_plugin_manager
from ...core.client import ArtifactType
from ...core.models import Attachment, Severity, TestResult
from ..artifacts import AttachmentService
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
        """Attach a file, bytes, or stream to the current test.

        This method uses AttachmentService to prepare the attachment consistently
        with caching, MIME detection, and hash computation.
        """
        ctx = self.test_ctx
        if not ctx:
            return

        session = self.session_ctx
        if not session or not session.config:
            # Fallback config if session not properly initialized
            config = ProofyConfig()
        elif isinstance(session.config, ProofyConfig):
            config = session.config
        else:
            # session.config is dict, create ProofyConfig from it
            config = ProofyConfig(**session.config)

        # Use AttachmentService to prepare the attachment
        service = AttachmentService(config=config)

        try:
            prepared = service.prepare_attachment(
                file=file,
                name=name,
                mime_type=mime_type,
                extension=extension,
                artifact_type=artifact_type,
            )

            # Determine original path string for tracking
            if isinstance(file, str | Path):
                original_path_string = str(file)
            elif isinstance(file, bytes | bytearray):
                original_path_string = "<bytes>"
            else:
                original_path_string = "<stream>"

            # Add to test context
            ctx.attachments.append(
                Attachment(
                    name=prepared.filename,
                    path=str(prepared.path) if isinstance(prepared.path, Path) else "<bytes>",
                    original_path=original_path_string,
                    mime_type=prepared.mime_type,
                    extension=extension,
                    size_bytes=prepared.size_bytes,
                    sha256=prepared.sha256,
                    artifact_type=int(prepared.artifact_type),
                )
            )
        except Exception as e:
            # Log error but don't fail the test
            import logging

            logger = logging.getLogger("Proofy")
            logger.error(f"Failed to attach {name}: {e}")
