"""Models for artifact handling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ...core.client import ArtifactType


@dataclass
class PreparedAttachment:
    """Represents a fully prepared attachment ready for upload.

    This model consolidates all necessary metadata and content for an artifact,
    eliminating the need to scatter this logic across multiple components.
    """

    path: str | Path | bytes
    """File path (str/Path) or in-memory bytes content."""

    filename: str
    """Display name for the attachment."""

    mime_type: str
    """MIME type (e.g., 'image/png', 'text/plain')."""

    size_bytes: int
    """Size of the attachment in bytes."""

    sha256: str
    """SHA-256 hexadecimal digest of the content."""

    artifact_type: ArtifactType | int
    """Type of artifact (ATTACHMENT, TRACE, SCREENSHOT, etc.)."""
