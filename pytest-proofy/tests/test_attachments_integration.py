from pathlib import Path
from unittest.mock import Mock

import pytest
from proofy.hooks.manager import get_plugin_manager, reset_plugin_manager
from proofy.runtime.api import add_attachment
from proofy.runtime.context import TestContext, set_current_test_context
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

    # Prepare existing result with server_id (required for upload)
    from proofy import ResultStatus, TestResult

    test_id = "node1"
    result = TestResult(
        id=test_id,
        name="Test 1",
        path="test_file.py",
        run_id=42,
        status=ResultStatus.PASSED,
        outcome="passed",
    )
    result.server_id = 1001
    plugin.test_results[test_id] = result

    # Ensure hook targets this plugin instance
    monkeypatch.setattr("pytest_proofy.plugin._plugin_instance", plugin, raising=False)

    # Set current test context with matching test_id
    set_current_test_context(TestContext(test_id=test_id))

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

    # And: result has one attachment with remote_id and original path (no cache)
    assert len(plugin.test_results[test_id].attachments) == 1
    att = plugin.test_results[test_id].attachments[0]
    assert att.path == str(src)
    assert att.remote_id == "att-xyz"
    assert ".attachments_cache" not in att.path


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

    from proofy import ResultStatus, TestResult

    test_id = "node2"
    result = TestResult(
        id=test_id,
        name="Test 2",
        path="test_file.py",
        run_id=42,
        status=ResultStatus.PASSED,
        outcome="passed",
    )
    result.server_id = 2002
    plugin.test_results[test_id] = result

    monkeypatch.setattr("pytest_proofy.plugin._plugin_instance", plugin, raising=False)

    # Create a temp file to attach; with cache enabled, commons should copy it
    src = tmp_path / "cache_enabled.txt"
    src.write_text("cache enabled content")

    # When: add attachment (no immediate upload since cache enabled)
    set_current_test_context(TestContext(test_id=test_id))
    add_attachment(file=str(src), name="Deferred", mime_type="text/plain")

    # Then: no immediate upload
    mock_client.upload_attachment_s3.assert_not_called()

    # And path stored is cached
    assert len(plugin.test_results[test_id].attachments) == 1
    att = plugin.test_results[test_id].attachments[0]
    assert ".attachments_cache" in att.path

    # When: sending result in live mode uploads the cached file
    plugin._send_result_live(result)

    mock_client.upload_attachment_s3.assert_called_once()
    args, kwargs = mock_client.upload_attachment_s3.call_args
    assert kwargs.get("result_id") == 2002
    assert kwargs.get("file_name") == "Deferred"
    assert kwargs.get("file_path") == att.path
    assert kwargs.get("content_type") == "text/plain"
