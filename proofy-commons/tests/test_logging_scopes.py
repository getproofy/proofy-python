"""Tests for scoped httpx logging helpers (no global impact)."""

from __future__ import annotations

import logging

from proofy._internal import logging_scopes


def _emit_httpx_info(message: str) -> None:
    """Helper to emit an INFO-level httpx log."""
    logging.getLogger("httpx").info(message)


def test_outside_scope_logging_is_unaffected(monkeypatch, caplog):
    """Outside the scope, user logging config is not altered by the module."""
    monkeypatch.delenv("PROOFYDEBUG", raising=False)
    httpx_logger = logging.getLogger("httpx")
    previous_level = httpx_logger.level
    try:
        httpx_logger.setLevel(logging.DEBUG)
        caplog.set_level(logging.DEBUG, logger="httpx")

        _emit_httpx_info("outside-visible")

        assert any(record.getMessage() == "outside-visible" for record in caplog.records)
    finally:
        httpx_logger.setLevel(previous_level)


def test_httpx_logs_hidden_inside_scope_when_debug_disabled(monkeypatch, caplog):
    """Inside scope, with PROOFYDEBUG disabled, INFO logs are suppressed."""
    monkeypatch.setenv("PROOFYDEBUG", "false")
    httpx_logger = logging.getLogger("httpx")
    previous_level = httpx_logger.level
    try:
        httpx_logger.setLevel(logging.DEBUG)
        caplog.set_level(logging.DEBUG, logger="httpx")

        with logging_scopes.httpx_debug_logging_scope():
            _emit_httpx_info("hidden-inside-scope")

        assert not any(record.getMessage() == "hidden-inside-scope" for record in caplog.records)
    finally:
        httpx_logger.setLevel(previous_level)


def test_httpx_logs_visible_inside_scope_when_debug_enabled(monkeypatch, caplog):
    """With PROOFYDEBUG enabled, entering scope exposes httpx INFO logs."""
    monkeypatch.setenv("PROOFYDEBUG", "true")
    httpx_logger = logging.getLogger("httpx")
    previous_level = httpx_logger.level
    try:
        httpx_logger.setLevel(logging.DEBUG)
        caplog.set_level(logging.DEBUG, logger="httpx")

        with logging_scopes.httpx_debug_logging_scope():
            _emit_httpx_info("visible-inside-scope")

        assert any(record.getMessage() == "visible-inside-scope" for record in caplog.records)
    finally:
        httpx_logger.setLevel(previous_level)
