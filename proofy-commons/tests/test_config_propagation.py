"""Tests for config propagation through system components (Phase 1)."""

from __future__ import annotations

from proofy._internal.config import ProofyConfig
from proofy._internal.context.models import SessionContext
from proofy._internal.context.service import ContextService
from proofy._internal.results.result_handler import ResultsHandler


class TestConfigPropagation:
    """Test that configuration values are properly propagated through components."""

    def test_batch_size_from_config(self):
        """Test that batch_size is taken from config, not environment variable."""
        config = ProofyConfig(
            enabled=True,
            mode="batch",  # Must be batch mode to create buffer
            batch_size=50,
            api_base="https://api.test.com",
            token="test-token",
            project_id=123,
        )
        handler = ResultsHandler(config=config, framework="pytest", disable_output=False)

        # In batch mode, buffer should be created with config batch_size
        assert handler.buffer is not None
        assert handler.buffer.batch_size == 50

    def test_batch_size_default(self):
        """Test that default batch_size is used when not specified."""
        config = ProofyConfig(
            enabled=True,
            mode="batch",  # Must be batch mode to create buffer
            api_base="https://api.test.com",
            token="test-token",
            project_id=123,
        )
        handler = ResultsHandler(config=config, framework="pytest", disable_output=False)

        # Default batch_size from ProofyConfig should be 100
        assert handler.buffer is not None
        assert handler.buffer.batch_size == 100

    def test_mode_from_session_context(self):
        """Test that mode is accessible from session context config."""
        config = ProofyConfig(mode="batch")
        session = SessionContext(
            session_id="test-session-123",
            config=config,
            run_name="Test Run",
        )

        assert session.config is not None
        assert session.config.mode == "batch"

    def test_session_context_with_config(self):
        """Test that session context properly stores config reference."""
        config = ProofyConfig(
            mode="lazy",
            batch_size=25,
            api_base="https://api.test.com",
            token="test-token",
            project_id=456,
        )

        service = ContextService()
        session = service.start_session(config=config, run_name="Test Run")

        assert session.config is not None
        assert session.config.mode == "lazy"
        assert session.config.batch_size == 25
        assert session.config.project_id == 456

    def test_config_modes(self):
        """Test all valid mode values."""
        for mode in ["live", "batch", "lazy"]:
            config = ProofyConfig(mode=mode)
            assert config.mode == mode

    def test_results_handler_uses_config_mode(self):
        """Test that ResultsHandler uses mode from config."""
        config = ProofyConfig(
            enabled=True,
            mode="lazy",
            api_base="https://api.test.com",
            token="test-token",
            project_id=789,
        )
        handler = ResultsHandler(config=config, framework="pytest", disable_output=True)

        assert handler.config.mode == "lazy"

    def test_context_service_attach_uses_session_mode(self):
        """Test that ContextService.attach() gets mode from session config."""
        config = ProofyConfig(
            mode="batch",
            api_base="https://api.test.com",
            token="test-token",
            project_id=100,
        )

        service = ContextService()
        service.start_session(config=config, run_name="Test")

        # Verify session has config
        assert service.session_ctx is not None
        assert service.session_ctx.config is not None
        assert service.session_ctx.config.mode == "batch"
