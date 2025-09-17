"""Tests for pytest-proofy configuration."""

import os
import pytest
from unittest.mock import Mock

from pytest_proofy.config import ProofyConfig, resolve_options


class TestProofyConfig:
    """Tests for ProofyConfig class."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ProofyConfig()
        
        assert config.mode == "lazy"
        assert config.api_base is None
        assert config.token is None
        assert config.project_id is None
        assert config.batch_size == 10
        assert config.output_dir == "proofy-artifacts"
        assert config.always_backup is False
        assert config.run_id is None
        assert config.run_name is None
        assert config.enable_attachments is True
        assert config.enable_hooks is True
        assert config.timeout_s == 30.0
        assert config.max_retries == 3
    
    def test_custom_config(self):
        """Test custom configuration values."""
        config = ProofyConfig(
            mode="live",
            api_base="https://api.example.com",
            token="test-token",
            project_id=123,
            batch_size=50,
            timeout_s=60.0
        )
        
        assert config.mode == "live"
        assert config.api_base == "https://api.example.com"
        assert config.token == "test-token"
        assert config.project_id == 123
        assert config.batch_size == 50
        assert config.timeout_s == 60.0


class TestResolveOptions:
    """Tests for resolve_options function."""
    
    def setup_method(self):
        """Clear environment variables before each test."""
        env_vars = [
            "PROOFY_MODE", "PROOFY_API_BASE", "PROOFY_TOKEN", "PROOFY_PROJECT_ID",
            "PROOFY_BATCH_SIZE", "PROOFY_TIMEOUT", "PROOFY_MAX_RETRIES"
        ]
        for var in env_vars:
            if var in os.environ:
                del os.environ[var]
    
    def test_default_resolution(self):
        """Test resolution with default values."""
        mock_config = Mock()
        mock_config.getoption.return_value = None
        mock_config.getini.return_value = ""
        
        config = resolve_options(mock_config)
        
        assert config.mode == "lazy"
        assert config.api_base is None
        assert config.batch_size == 10
    
    def test_cli_option_priority(self):
        """Test that CLI options have highest priority."""
        mock_config = Mock()
        mock_config.getoption.side_effect = lambda name, default=None: {
            "proofy_mode": "live",
            "proofy_api_base": "https://cli.example.com",
            "proofy_batch_size": 25,
        }.get(name, default)
        mock_config.getini.return_value = ""
        
        # Set environment variables that should be overridden
        os.environ["PROOFY_MODE"] = "batch"
        os.environ["PROOFY_API_BASE"] = "https://env.example.com"
        
        config = resolve_options(mock_config)
        
        # CLI values should win
        assert config.mode == "live"
        assert config.api_base == "https://cli.example.com"
        assert config.batch_size == 25
    
    def test_env_variable_priority(self):
        """Test that environment variables override ini values."""
        mock_config = Mock()
        mock_config.getoption.return_value = None
        mock_config.getini.side_effect = lambda name: {
            "proofy_mode": "batch",
            "proofy_api_base": "https://ini.example.com",
        }.get(name, "")
        
        # Set environment variables
        os.environ["PROOFY_MODE"] = "live"
        os.environ["PROOFY_API_BASE"] = "https://env.example.com"
        os.environ["PROOFY_BATCH_SIZE"] = "30"
        
        config = resolve_options(mock_config)
        
        # Environment values should win over ini
        assert config.mode == "live"
        assert config.api_base == "https://env.example.com"
        assert config.batch_size == 30
    
    def test_ini_fallback(self):
        """Test fallback to ini values."""
        mock_config = Mock()
        mock_config.getoption.return_value = None
        mock_config.getini.side_effect = lambda name: {
            "proofy_mode": "batch",
            "proofy_api_base": "https://ini.example.com",
            "proofy_batch_size": "15",
        }.get(name, "")
        
        config = resolve_options(mock_config)
        
        assert config.mode == "batch"
        assert config.api_base == "https://ini.example.com"
        assert config.batch_size == 15
    
    def test_type_conversion(self):
        """Test proper type conversion from strings."""
        mock_config = Mock()
        mock_config.getoption.return_value = None
        mock_config.getini.return_value = ""
        
        # Set environment variables as strings
        os.environ["PROOFY_PROJECT_ID"] = "456"
        os.environ["PROOFY_BATCH_SIZE"] = "20"
        os.environ["PROOFY_TIMEOUT"] = "45.5"
        os.environ["PROOFY_MAX_RETRIES"] = "5"
        os.environ["PROOFY_ALWAYS_BACKUP"] = "true"
        
        config = resolve_options(mock_config)
        
        assert config.project_id == 456
        assert config.batch_size == 20
        assert config.timeout_s == 45.5
        assert config.max_retries == 5
        assert config.always_backup is True
    
    def test_invalid_type_conversion(self):
        """Test handling of invalid type conversions."""
        mock_config = Mock()
        mock_config.getoption.return_value = None
        mock_config.getini.return_value = ""
        
        # Set invalid values
        os.environ["PROOFY_PROJECT_ID"] = "invalid"
        os.environ["PROOFY_BATCH_SIZE"] = "not-a-number"
        
        config = resolve_options(mock_config)
        
        # Should fall back to defaults
        assert config.project_id is None
        assert config.batch_size == 10
