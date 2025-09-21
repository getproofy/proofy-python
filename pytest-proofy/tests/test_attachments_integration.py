from pathlib import Path
from unittest.mock import Mock

import pytest
from proofy import TestResult as TestContext
from proofy import set_current_test_context
from proofy.api import add_attachment
from proofy.hooks.manager import get_plugin_manager, reset_plugin_manager
from pytest_proofy.config import ProofyConfig
from pytest_proofy.plugin import ProofyPytestPlugin, PytestProofyHooks


def test_live_mode_immediate_upload_without_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Given: live mode with cache disabled via env
    monkeypatch.setenv("PROOFY_MODE", "live")
    monkeypatch.setenv("PROOFY_DISABLE_ATTACHMENT_CACHE", "true")

    reset_plugin_manager()
    pm = get_plugin_manager()
    pm.register(PytestProofyHooks())

    # Prepare plugin with live mode and mock client
    config = ProofyConfig(mode="live", api_base="https://api.example.com", token="tkn")
    plugin = ProofyPytestPlugin(config)
    plugin.run_id = 42

    mock_client = Mock()
    mock_client.upload_attachment_s3.return_value = {"attachment_id": "att-xyz"}
    plugin.client = mock_client

    # Prepare current context with server_id (required for upload)
    test_id = "node1"
    set_current_test_context(TestContext(test_id=test_id))
    ctx = get_plugin_manager()  # no-op to keep hook manager initialized
    from proofy import get_current_test_context as _ctx

    _ctx().server_id = 1001

    # Ensure hook targets this plugin instance
    monkeypatch.setattr("pytest_proofy.plugin._plugin_instance", plugin, raising=False)

    # Set current test context with matching test_id (already set above)

    # Create a temp file to attach
    src = tmp_path / "immediate.txt"
    src.write_text("immediate upload")

    # When: add attachment (should trigger immediate upload, no caching)
    add_attachment(file=str(src), name="Immediate", mime_type="text/plain")

    # Then: upload called with correct params
    mock_client.upload_attachment_s3.assert_called_once()
    args, kwargs = mock_client.upload_attachment_s3.call_args
    assert kwargs.get("result_id") == 1001
    assert kwargs.get("file_name") == "Immediate"
    assert kwargs.get("file_path") == str(src)
    assert kwargs.get("content_type") == "text/plain"

    # And: context recorded original path (no cache)
    from proofy import get_current_test_context as _ctx

    files = _ctx().files
    assert len(files) == 1
    assert files[0]["path"] == str(src)
    assert ".attachments_cache" not in files[0]["path"]


def test_live_mode_upload_during_send_with_cache_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    # Given: live mode with cache enabled (default), output dir set
    monkeypatch.setenv("PROOFY_MODE", "live")
    monkeypatch.setenv("PROOFY_OUTPUT_DIR", str(tmp_path / "artifacts"))
    monkeypatch.delenv("PROOFY_DISABLE_ATTACHMENT_CACHE", raising=False)

    reset_plugin_manager()
    pm = get_plugin_manager()
    pm.register(PytestProofyHooks())

    config = ProofyConfig(mode="live", api_base="https://api.example.com", token="tkn")
    plugin = ProofyPytestPlugin(config)
    plugin.run_id = 42

    mock_client = Mock()
    plugin.client = mock_client

    test_id = "node2"
    set_current_test_context(TestContext(test_id=test_id))
    from proofy import get_current_test_context as _ctx

    _ctx().server_id = 2002

    monkeypatch.setattr("pytest_proofy.plugin._plugin_instance", plugin, raising=False)

    # Create a temp file to attach; with cache enabled, commons should copy it
    src = tmp_path / "cache_enabled.txt"
    src.write_text("cache enabled content")

    # When: add attachment (no immediate upload since cache enabled)
    add_attachment(file=str(src), name="Deferred", mime_type="text/plain")

    # Then: no immediate upload
    mock_client.upload_attachment_s3.assert_not_called()

    # And path stored is cached in context files
    from proofy import get_current_test_context as _ctx

    files = _ctx().files
    assert len(files) == 1
    assert ".attachments_cache" in files[0]["path"]

    # When: sending result in live mode uploads the cached file
    # Build a minimal result and send live; handler will use context server_id
    from proofy import TestResult

    result = TestResult(id=test_id, name="Test 2", path="test_file.py", run_id=42, outcome="passed")
    plugin._send_result_live(result)

    mock_client.upload_attachment_s3.assert_called_once()
    args, kwargs = mock_client.upload_attachment_s3.call_args
    assert kwargs.get("result_id") == 2002
    assert kwargs.get("file_name") == "Deferred"
    # Compare with cached path stored in context
    from proofy import get_current_test_context as _ctx

    cached_path = _ctx().files[0]["path"]
    assert kwargs.get("file_path") == cached_path
    assert kwargs.get("content_type") == "text/plain"
