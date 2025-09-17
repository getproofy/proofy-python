from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path


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
    """Return the base output directory for artifacts."""
    raw = os.getenv("PROOFY_OUTPUT_DIR", "proofy-artifacts")
    return Path(raw)


def ensure_cache_dir() -> Path:
    """Ensure and return the cache directory path for attachments."""
    base = get_output_dir()
    cache_dir = base / ".attachments_cache"
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
    return ".attachments_cache" in p.parts


def cache_attachment(src_path: str | Path) -> Path:
    """Copy the attachment file to the cache directory and return the new path.

    The destination filename is randomized to avoid collisions while preserving
    the original file extension.
    """
    source = Path(src_path)
    cache_dir = ensure_cache_dir()
    extension = source.suffix
    dest_name = f"{uuid.uuid4().hex}{extension}"
    dest = cache_dir / dest_name
    shutil.copy2(source, dest)
    return dest
