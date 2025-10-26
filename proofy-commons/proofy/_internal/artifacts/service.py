"""Unified attachment preparation functions.

This module consolidates attachment handling logic that was previously scattered
across ContextService, ArtifactUploader, and other components.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import IO

from ...core.client import ArtifactType
from ...core.client.base import ClientHelpers
from .attachments_cache import (
    cache_attachment,
    cache_attachment_from_bytes,
    cache_attachment_from_stream,
    is_cached_path,
    should_cache_for_mode,
)
from .models import PreparedAttachment


def prepare_attachment(
    file: str | Path | bytes | bytearray | IO[bytes],
    *,
    name: str,
    mode: str | None = None,
    mime_type: str | None = None,
    extension: str | None = None,
    artifact_type: ArtifactType | int = ArtifactType.ATTACHMENT,
) -> PreparedAttachment:
    """Prepare an attachment for upload.

    This function handles all the complexity of:
    - Caching based on mode
    - MIME type detection
    - Hash and size computation
    - Consistent handling of different input types (path, bytes, stream)

    Args:
        file: File path, bytes, or stream
        name: Display name for the attachment
        mode: Proofy mode (live/batch/lazy) - affects caching behavior
        mime_type: Optional MIME type (auto-detected if not provided)
        extension: Optional file extension for MIME detection
        artifact_type: Type of artifact (default: ATTACHMENT)

    Returns:
        PreparedAttachment with all metadata populated

    Raises:
        ValueError: If file path doesn't exist
        IOError: If file cannot be read
    """
    path_to_store: Path | bytes
    cached_size: int | None = None
    cached_sha: str | None = None

    # Determine if we should cache based on mode
    should_cache = should_cache_for_mode(mode)

    # Handle different input types
    if isinstance(file, str | Path):
        # Path-like input
        original_path = Path(file)
        if not original_path.exists():
            raise ValueError(f"File not found: {file}")

        path_to_store = original_path

        # Cache if needed and not already cached
        if should_cache and not is_cached_path(path_to_store):
            path_to_store, cached_size, cached_sha = cache_attachment(path_to_store)

    elif isinstance(file, bytes | bytearray):
        # In-memory bytes
        suffix = f".{extension}" if extension else None
        path_to_store, cached_size, cached_sha = cache_attachment_from_bytes(
            bytes(file), suffix=suffix
        )

    else:
        # Stream input
        suffix = f".{extension}" if extension else None
        path_to_store, cached_size, cached_sha = cache_attachment_from_stream(file, suffix=suffix)

    # Compute MIME type if not provided
    if mime_type is None:
        if extension:
            mime_type, _ = mimetypes.guess_type(f"file.{extension}")
        elif isinstance(path_to_store, Path):
            mime_type, _ = mimetypes.guess_type(str(path_to_store))

        # Default fallback
        mime_type = mime_type or "application/octet-stream"

    # Compute size and hash if not already done by caching
    if cached_size is None or cached_sha is None:
        # At this point, path_to_store is always a Path because
        # all cache functions return Path as the first element
        cached_size, cached_sha = ClientHelpers.compute_file_hash(path_to_store)

    # Normalize artifact_type to ArtifactType enum
    if isinstance(artifact_type, int):
        artifact_type = ArtifactType(artifact_type)

    return PreparedAttachment(
        path=path_to_store,
        filename=name,
        mime_type=mime_type,
        size_bytes=cached_size,
        sha256=cached_sha,
        artifact_type=artifact_type,
    )


def prepare_traceback(text: str, base_name: str) -> PreparedAttachment:
    """Prepare a traceback as a text attachment.

    Args:
        text: Traceback text content
        base_name: Base name for the file (will be sanitized and suffixed)

    Returns:
        PreparedAttachment with traceback ready for upload
    """
    # Sanitize filename
    safe_name = "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in str(base_name))
    filename = f"{safe_name[:64]}-traceback.txt"

    # Convert to bytes
    data_bytes = text.encode("utf-8", errors="replace")

    # Compute hash and size
    size_bytes, sha256 = ClientHelpers.compute_bytes_hash(data_bytes)

    # Cache the traceback
    path, _, _ = cache_attachment_from_bytes(data_bytes, suffix=".txt")

    return PreparedAttachment(
        path=path,
        filename=filename,
        mime_type="text/plain",
        size_bytes=size_bytes,
        sha256=sha256,
        artifact_type=ArtifactType.TRACE,
    )
