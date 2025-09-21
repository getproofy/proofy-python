from pathlib import Path

import pytest
from proofy.api import add_attachment, get_current_test_context, set_current_test_context
from proofy.hooks.manager import get_plugin_manager, reset_plugin_manager
from proofy.hooks.specs import hookimpl


@pytest.fixture(autouse=True)
def clean_ctx():
    set_current_test_context(None)
    reset_plugin_manager()
    yield
    set_current_test_context(None)
    reset_plugin_manager()


def test_add_attachment_caches_file_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Given
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    src_file = src_dir / "example.txt"
    src_file.write_text("hello world")

    monkeypatch.setenv("PROOFY_MODE", "lazy")
    monkeypatch.setenv("PROOFY_OUTPUT_DIR", str(out_dir))
    monkeypatch.delenv("PROOFY_DISABLE_ATTACHMENT_CACHE", raising=False)

    # When
    add_attachment(file=str(src_file), name="example", mime_type="text/plain")

    # Then
    ctx = get_current_test_context()
    assert len(ctx.files) == 1
    info = ctx.files[0]

    cached_path = Path(info["path"])  # path should be cached
    assert ".attachments_cache" in cached_path.parts
    assert cached_path.exists()
    assert (out_dir / ".attachments_cache").exists()
    assert info.get("original_path") == str(src_file)
    assert cached_path.read_text() == "hello world"


def test_add_attachment_no_cache_in_live_mode_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # Given
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    src_file = tmp_path / "live.txt"
    src_file.write_text("live content")

    monkeypatch.setenv("PROOFY_MODE", "live")
    monkeypatch.setenv("PROOFY_OUTPUT_DIR", str(out_dir))
    monkeypatch.setenv("PROOFY_DISABLE_ATTACHMENT_CACHE", "true")

    # When
    add_attachment(file=str(src_file), name="live", mime_type="text/plain")

    # Then
    ctx = get_current_test_context()
    assert len(ctx.files) == 1
    info = ctx.files[0]
    # Path should remain original when caching is disabled in live mode
    assert info["path"] == str(src_file)
    # Cache directory should not contain the file
    cache_dir = out_dir / ".attachments_cache"
    if cache_dir.exists():
        assert not any(p.name.endswith(".txt") for p in cache_dir.iterdir())


def test_hook_receives_cached_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Given
    out_dir = tmp_path / "artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    src_file = tmp_path / "hook.txt"
    src_file.write_text("hook content")

    monkeypatch.setenv("PROOFY_MODE", "batch")
    monkeypatch.setenv("PROOFY_OUTPUT_DIR", str(out_dir))
    monkeypatch.delenv("PROOFY_DISABLE_ATTACHMENT_CACHE", raising=False)

    class CapturePlugin:
        def __init__(self):
            self.calls = []

        @hookimpl
        def proofy_add_attachment(self, test_id, file_path, name, mime_type=None):
            self.calls.append((test_id, file_path, name, mime_type))

    plugin = CapturePlugin()
    pm = get_plugin_manager()
    pm.register(plugin)

    # When
    add_attachment(file=str(src_file), name="hook-file", mime_type="text/plain")

    # Then
    ctx = get_current_test_context()
    info = ctx.files[0]
    assert len(plugin.calls) == 1
    _test_id, hook_path, _name, _mime = plugin.calls[0]
    assert hook_path == info["path"]
    assert ".attachments_cache" in Path(hook_path).parts


def test_add_attachment_fallback_when_source_missing(monkeypatch: pytest.MonkeyPatch):
    # Given
    missing_path = Path("/tmp/does_not_exist_file.txt")
    monkeypatch.setenv("PROOFY_MODE", "lazy")
    monkeypatch.delenv("PROOFY_DISABLE_ATTACHMENT_CACHE", raising=False)
    monkeypatch.delenv("PROOFY_OUTPUT_DIR", raising=False)

    # When: Should not raise, and should fall back to original path
    add_attachment(file=str(missing_path), name="missing", mime_type="text/plain")

    # Then
    ctx = get_current_test_context()
    info = ctx.files[0]
    assert info["path"] == str(missing_path)
