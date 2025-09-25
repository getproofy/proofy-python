from __future__ import annotations

import hashlib
import os
import tempfile
import uuid
from pathlib import Path
from typing import IO


def _parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def is_cache_enabled() -> bool:
    """Return True if local attachment caching is enabled.

    Controlled by env var PROOFY_DISABLE_ATTACHMENT_CACHE (default: False).
    """
    return not _parse_bool(os.getenv("PROOFY_DISABLE_ATTACHMENT_CACHE"))


def get_output_dir() -> Path:
    """Return the base output directory for artifacts (non-cache outputs)."""
    raw = os.getenv("PROOFY_OUTPUT_DIR", "proofy-artifacts")
    return Path(raw)


def ensure_cache_dir() -> Path:
    """Ensure and return the GLOBAL temp cache directory for attachments.

    Uses the system temp directory by default. Override root via PROOFY_TEMP_DIR.
    The directory structure is <temp_root>/proofy/attachments_cache to avoid collisions.
    """
    temp_root = Path(os.getenv("PROOFY_TEMP_DIR", tempfile.gettempdir()))
    cache_dir = temp_root / "proofy" / "attachments_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def should_cache_for_mode(mode: str | None) -> bool:
    """Decide if we should cache attachments for the given mode.

    We skip caching when running in live mode AND caching is disabled.
    In all other cases, we cache to ensure availability after tests.
    """
    return not ((mode or "").lower() == "live" and not is_cache_enabled())


def is_cached_path(path: str | Path) -> bool:
    p = Path(path)
    try:
        return p.resolve().is_relative_to(ensure_cache_dir().resolve())
    except Exception:
        # Fallback for older Python or resolution issues
        return str(ensure_cache_dir().resolve()) in str(p.resolve())


def cache_attachment(src_path: str | Path) -> tuple[Path, int, str]:
    """Copy a file to the cache directory and return (new_path, size, sha256).

    Performs a single-pass copy while computing size and SHA-256.
    The destination filename is randomized and preserves the original extension.
    """
    source = Path(src_path)
    print(f"Caching attachment from {source} to {ensure_cache_dir()}")
    cache_dir = ensure_cache_dir()
    extension = source.suffix
    dest_name = f"{uuid.uuid4().hex}{extension}"
    dest = cache_dir / dest_name
    sha256 = hashlib.sha256()
    total = 0
    with open(source, "rb") as rf, open(dest, "wb") as wf:
        while True:
            chunk = rf.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            sha256.update(chunk)
            wf.write(chunk)
    return dest, total, sha256.hexdigest()


def cache_attachment_from_bytes(data: bytes, *, suffix: str | None = None) -> tuple[Path, int, str]:
    """Write bytes to a new cached file in one pass and return (path, size, sha256).

    The filename is randomized; optional suffix (e.g., ".png").
    """
    cache_dir = ensure_cache_dir()
    dest_name = f"{uuid.uuid4().hex}{suffix or ''}"
    dest = cache_dir / dest_name
    sha256 = hashlib.sha256()
    sha256.update(data)
    size_bytes = len(data)
    with open(dest, "wb") as f:
        f.write(data)
    return dest, size_bytes, sha256.hexdigest()


def cache_attachment_from_stream(
    stream: IO[bytes], *, suffix: str | None = None
) -> tuple[Path, int, str]:
    """Stream to a new cached file in one pass and return (path, size, sha256)."""
    cache_dir = ensure_cache_dir()
    dest_name = f"{uuid.uuid4().hex}{suffix or ''}"
    dest = cache_dir / dest_name
    sha256 = hashlib.sha256()
    total = 0
    with open(dest, "wb") as f:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            sha256.update(chunk)
            f.write(chunk)
    return dest, total, sha256.hexdigest()
