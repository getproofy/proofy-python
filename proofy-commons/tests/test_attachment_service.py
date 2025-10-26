"""Tests for AttachmentService (Phase 2)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from proofy._internal.artifacts import AttachmentService, PreparedAttachment
from proofy._internal.config import ProofyConfig
from proofy.core.client import ArtifactType


class TestAttachmentService:
    """Test AttachmentService attachment preparation."""

    @pytest.fixture
    def config_live(self) -> ProofyConfig:
        """Config with live mode (minimal caching)."""
        return ProofyConfig(mode="live", cache_attachments=False)

    @pytest.fixture
    def config_batch(self) -> ProofyConfig:
        """Config with batch mode (always cache)."""
        return ProofyConfig(mode="batch", cache_attachments=True)

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        """Create a temporary file with some content."""
        file = tmp_path / "test_file.txt"
        file.write_text("Hello, Proofy!")
        return file

    def test_prepare_attachment_from_path(
        self, config_batch: ProofyConfig, temp_file: Path
    ) -> None:
        """Test preparing attachment from file path."""
        service = AttachmentService(config=config_batch)

        prepared = service.prepare_attachment(
            file=temp_file,
            name="test.txt",
            mime_type="text/plain",
        )

        assert isinstance(prepared, PreparedAttachment)
        assert prepared.filename == "test.txt"
        assert prepared.mime_type == "text/plain"
        assert prepared.size_bytes > 0
        assert len(prepared.sha256) == 64  # SHA-256 hex digest length
        assert prepared.artifact_type == ArtifactType.ATTACHMENT

    def test_prepare_attachment_from_bytes(self, config_batch: ProofyConfig) -> None:
        """Test preparing attachment from bytes."""
        service = AttachmentService(config=config_batch)
        content = b"Binary content here"

        prepared = service.prepare_attachment(
            file=content,
            name="data.bin",
            extension="bin",
        )

        assert prepared.filename == "data.bin"
        assert prepared.size_bytes == len(content)
        assert len(prepared.sha256) == 64
        assert prepared.artifact_type == ArtifactType.ATTACHMENT

    def test_prepare_attachment_from_stream(self, config_batch: ProofyConfig) -> None:
        """Test preparing attachment from stream."""
        service = AttachmentService(config=config_batch)
        content = b"Stream content"
        stream = io.BytesIO(content)

        prepared = service.prepare_attachment(
            file=stream,
            name="stream.dat",
            mime_type="application/octet-stream",
        )

        assert prepared.filename == "stream.dat"
        assert prepared.mime_type == "application/octet-stream"
        assert prepared.size_bytes == len(content)

    def test_prepare_attachment_mime_detection(
        self, config_batch: ProofyConfig, tmp_path: Path
    ) -> None:
        """Test automatic MIME type detection."""
        service = AttachmentService(config=config_batch)

        # Create PNG file (just header, not real PNG)
        png_file = tmp_path / "image.png"
        png_file.write_bytes(b"\x89PNG\r\n\x1a\n")

        prepared = service.prepare_attachment(
            file=png_file,
            name="test.png",
        )

        # Should auto-detect as image/png
        assert prepared.mime_type == "image/png"

    def test_prepare_attachment_with_extension(self, config_batch: ProofyConfig) -> None:
        """Test MIME detection using extension parameter."""
        service = AttachmentService(config=config_batch)

        prepared = service.prepare_attachment(
            file=b"JSON content",
            name="config.json",
            extension="json",
        )

        # Should detect as application/json based on extension
        assert prepared.mime_type == "application/json"

    def test_prepare_attachment_missing_file(self, config_batch: ProofyConfig) -> None:
        """Test that preparing non-existent file raises error."""
        service = AttachmentService(config=config_batch)

        with pytest.raises(ValueError, match="File not found"):
            service.prepare_attachment(
                file="/nonexistent/path/to/file.txt",
                name="missing.txt",
            )

    def test_prepare_attachment_custom_artifact_type(self, config_batch: ProofyConfig) -> None:
        """Test preparing attachment with custom artifact type."""
        service = AttachmentService(config=config_batch)

        prepared = service.prepare_attachment(
            file=b"Screenshot data",
            name="screenshot.png",
            artifact_type=ArtifactType.SCREENSHOT,
        )

        assert prepared.artifact_type == ArtifactType.SCREENSHOT

    def test_prepare_traceback(self, config_batch: ProofyConfig) -> None:
        """Test preparing traceback as attachment."""
        service = AttachmentService(config=config_batch)

        traceback_text = """Traceback (most recent call last):
  File "test.py", line 10, in test_function
    raise ValueError("Test error")
ValueError: Test error
"""

        prepared = service.prepare_traceback(
            text=traceback_text,
            base_name="test_function",
        )

        assert "test_function" in prepared.filename
        assert prepared.filename.endswith("-traceback.txt")
        assert prepared.mime_type == "text/plain"
        assert prepared.artifact_type == ArtifactType.TRACE
        assert prepared.size_bytes == len(traceback_text.encode("utf-8"))
        assert len(prepared.sha256) == 64

    def test_prepare_traceback_sanitize_name(self, config_batch: ProofyConfig) -> None:
        """Test that traceback filename is properly sanitized."""
        service = AttachmentService(config=config_batch)

        prepared = service.prepare_traceback(
            text="Error!",
            base_name="test/with/slashes and spaces",
        )

        # Should sanitize special characters
        assert "/" not in prepared.filename
        assert " " not in prepared.filename
        assert prepared.filename.endswith("-traceback.txt")

    def test_prepare_traceback_long_name_truncation(self, config_batch: ProofyConfig) -> None:
        """Test that very long base names are truncated."""
        service = AttachmentService(config=config_batch)

        long_name = "a" * 100
        prepared = service.prepare_traceback(text="Error", base_name=long_name)

        # Filename should be truncated to 64 chars + suffix
        assert len(prepared.filename) <= 64 + len("-traceback.txt")

    def test_caching_behavior_batch_mode(self, config_batch: ProofyConfig, temp_file: Path) -> None:
        """Test that batch mode caches files."""
        service = AttachmentService(config=config_batch)

        prepared = service.prepare_attachment(
            file=temp_file,
            name="cached.txt",
        )

        # In batch mode, file should be cached
        # The path should be different from original (in cache dir)
        if isinstance(prepared.path, Path):
            assert prepared.path != temp_file
            assert prepared.path.exists()

    def test_mime_type_fallback(self, config_batch: ProofyConfig) -> None:
        """Test fallback to application/octet-stream when MIME unknown."""
        service = AttachmentService(config=config_batch)

        prepared = service.prepare_attachment(
            file=b"Unknown content",
            name="unknown",
            # No extension, no mime_type provided
        )

        # Should fall back to octet-stream
        assert prepared.mime_type == "application/octet-stream"

    def test_bytearray_input(self, config_batch: ProofyConfig) -> None:
        """Test that bytearray input is properly handled."""
        service = AttachmentService(config=config_batch)

        content = bytearray(b"Bytearray content")
        prepared = service.prepare_attachment(
            file=content,
            name="bytearray.bin",
        )

        assert prepared.size_bytes == len(content)
        assert len(prepared.sha256) == 64
