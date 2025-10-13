"""Configuration system for pytest-proofy plugin."""

from __future__ import annotations

import os
from typing import Any

import pytest
from proofy._internal.config import ProofyConfig


def register_options(parser: pytest.Parser) -> None:
    """Register pytest command line options for Proofy."""
    group = parser.getgroup("proofy", "Proofy test reporting")

    # Core options
    group.addoption(
        "--proofy-mode",
        action="store",
        default=None,
        choices=["live", "batch", "lazy"],
        help="Proofy delivery mode: live (real-time), batch (grouped), lazy (after completion)",
    )
    group.addoption(
        "--proofy-api-base",
        action="store",
        default=None,
        help="Proofy API base URL (e.g., https://api.proofy.dev)",
    )
    group.addoption(
        "--proofy-token",
        action="store",
        default=None,
        help="Proofy API authentication token",
    )
    group.addoption(
        "--proofy-project-id",
        action="store",
        type=int,
        default=None,
        help="Proofy project ID",
    )

    # Batch options
    group.addoption(
        "--proofy-batch-size",
        action="store",
        type=int,
        default=None,
        help="Number of results to batch together (batch mode only)",
    )

    # Output options
    group.addoption(
        "--proofy-output-dir",
        action="store",
        default=None,
        help="Directory for local backup exports",
    )
    group.addoption(
        "--proofy-always-backup",
        action="store_true",
        help="Always create local backup files",
    )

    # Run options
    group.addoption(
        "--proofy-run-id",
        action="store",
        type=int,
        default=None,
        help="Existing run ID to append results to",
    )
    group.addoption(
        "--proofy-run-name",
        action="store",
        default=None,
        help="Name for the test run",
    )
    group.addoption(
        "--proofy-run-attributes",
        action="store",
        default=None,
        help="Custom run attributes as key=value pairs separated by comma (e.g., environment=prod,version=1.0)",
    )


def resolve_options(config: pytest.Config) -> ProofyConfig:
    """Resolve Proofy configuration from CLI, environment, and pytest.ini.

    Priority: CLI > ENV > pytest.ini > defaults
    """

    def parse_bool(value: str | bool) -> bool:
        """Parse boolean from string."""
        if isinstance(value, bool):
            return value
        return value.lower() in ("true", "1", "yes", "on")

    def parse_attributes(value: str | None) -> dict[str, str] | None:
        """Parse attributes from key=value,key2=value2 format."""
        if not value:
            return None
        attrs = {}
        for pair in value.split(","):
            pair = pair.strip()
            if "=" in pair:
                key, val = pair.split("=", 1)
                attrs[key.strip()] = val.strip()
        return attrs if attrs else None

    def get_option(
        name: str,
        env_name: str,
        ini_name: str,
        default: Any = None,
        type_func: Any = None,
    ) -> Any:
        """Get option value with priority: CLI > ENV > INI > default."""
        # CLI option (highest priority)
        cli_value = config.getoption(name, default=None)
        if type_func is bool:
            if cli_value is True:
                return True
            # If False or None, fall through to ENV/INI/default
        else:
            if cli_value is not None:
                return cli_value

        # Environment variable
        env_value = os.getenv(env_name)
        if env_value is not None:
            if type_func:
                try:
                    if type_func is bool:
                        return parse_bool(env_value)
                    return type_func(env_value)
                except (ValueError, TypeError):
                    return default
            return env_value

        # pytest.ini value
        ini_value = config.getini(ini_name)
        if ini_value:
            if type_func:
                try:
                    if type_func is bool:
                        return parse_bool(ini_value)
                    return type_func(ini_value)
                except (ValueError, TypeError):
                    return default
            return ini_value

        return default

    # Resolve all configuration options
    proofy_config = ProofyConfig(
        mode=get_option("proofy_mode", "PROOFY_MODE", "proofy_mode"),
        api_base=get_option(
            "proofy_api_base",
            "PROOFY_API_BASE",
            "proofy_api_base",
        ),
        token=get_option("proofy_token", "PROOFY_TOKEN", "proofy_token"),
        project_id=get_option(
            "proofy_project_id", "PROOFY_PROJECT_ID", "proofy_project_id", type_func=int
        ),
        batch_size=get_option(
            "proofy_batch_size", "PROOFY_BATCH_SIZE", "proofy_batch_size", type_func=int
        ),
        output_dir=get_option(
            "proofy_output_dir",
            "PROOFY_OUTPUT_DIR",
            "proofy_output_dir",
        ),
        always_backup=get_option(
            "proofy_always_backup",
            "PROOFY_ALWAYS_BACKUP",
            "proofy_always_backup",
            type_func=bool,
        ),
        run_id=get_option("proofy_run_id", "PROOFY_RUN_ID", "proofy_run_id", type_func=int),
        run_name=get_option("proofy_run_name", "PROOFY_RUN_NAME", "proofy_run_name"),
    )

    attrs_str = get_option(
        "proofy_run_attributes", "PROOFY_RUN_ATTRIBUTES", "proofy_run_attributes"
    )
    if attrs_str:
        proofy_config.run_attributes = parse_attributes(attrs_str)

    return proofy_config


def setup_pytest_ini_options(parser: pytest.Parser) -> None:
    """Setup pytest.ini configuration options."""
    parser.addini("proofy_mode", "Proofy delivery mode")
    parser.addini("proofy_api_base", "Proofy API base URL")
    parser.addini("proofy_token", "Proofy API token")
    parser.addini("proofy_project_id", "Proofy project ID")
    parser.addini("proofy_batch_size", "Batch size for results")
    parser.addini("proofy_output_dir", "Output directory for backups")
    parser.addini("proofy_always_backup", "Always create backup files")
    parser.addini("proofy_run_id", "Existing run ID")
    parser.addini("proofy_run_name", "Test run name")
    parser.addini("proofy_run_attributes", "Custom run attributes (key=value,key2=value2)")
