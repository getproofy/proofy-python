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
    print(f"Caching attachment from {source} to {ensure_cache_dir()}")
    cache_dir = ensure_cache_dir()
    extension = source.suffix
    dest_name = f"{uuid.uuid4().hex}{extension}"
    dest = cache_dir / dest_name
    shutil.copy2(source, dest)
    return dest


def clear_attachments_cache(output_dir: str | Path | None = None) -> None:
    """Clear all cached attachments from .attachments_cache directory.

    Args:
        output_dir: Directory containing the cache. If None, uses default output directory.
    """
    try:
        import shutil
        from pathlib import Path

        output_path = get_output_dir() if output_dir is None else Path(output_dir)
        cache_dir = output_path / ".attachments_cache"

        if cache_dir.exists() and cache_dir.is_dir():
            # Count files before clearing
            cached_files = list(cache_dir.glob("*"))
            file_count = len([f for f in cached_files if f.is_file()])

            if file_count > 0:
                # Remove all files in cache directory
                for item in cached_files:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)

                print(f"Cleared {file_count} cached attachments from {cache_dir}")
            else:
                print(f"Cache directory {cache_dir} is already empty")

    except Exception as e:
        print(f"Failed to clear attachments cache: {e}")


def create_artifacts_zip(output_dir: str | Path) -> None:
    """Create a zip archive containing only cached attachments from .attachments_cache.

    The .attachments_cache folder is renamed to 'attachments' in the zip.

    Args:
        output_dir: Directory containing artifacts to zip
    """
    try:
        import zipfile
        from pathlib import Path

        output_path = Path(output_dir)
        zip_path = output_path / "artifacts.zip"
        cache_dir = output_path / ".attachments_cache"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Only add files from .attachments_cache directory
            if cache_dir.exists() and cache_dir.is_dir():
                for item in cache_dir.rglob("*"):
                    if item.is_file():
                        # Get relative path from cache_dir and rename folder
                        relative_path = item.relative_to(cache_dir)
                        # Change .attachments_cache to attachments in the zip
                        arcname = Path("attachments") / relative_path
                        zipf.write(item, arcname)

        # Check if zip has any contents
        with zipfile.ZipFile(zip_path, "r") as zipf:
            file_count = len(zipf.namelist())

        if file_count > 0:
            print(f"Artifacts archived to {zip_path} ({file_count} files)")
        else:
            print("No artifacts to archive, removing empty zip")
            zip_path.unlink()

    except Exception as e:
        print(f"Failed to create artifacts zip: {e}")
