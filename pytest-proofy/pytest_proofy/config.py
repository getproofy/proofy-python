"""Configuration system for pytest-proofy plugin."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

import pytest

Mode = Literal["live", "batch", "lazy"]


@dataclass
class ProofyConfig:
    """Configuration for pytest-proofy plugin."""

    # Core settings
    mode: Mode = "lazy"
    api_base: str | None = None
    token: str | None = None
    project_id: int | None = None

    # Batch settings
    batch_size: int = 10

    # Output settings
    output_dir: str = "proofy-artifacts"
    always_backup: bool = False

    cache_attachments: bool = True

    # Run settings
    run_id: int | None = None
    run_name: str | None = None

    # Feature flags
    enable_attachments: bool = True
    enable_hooks: bool = True

    # Timeout settings
    timeout_s: float = 30.0

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0


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
        help="Proofy API base URL (e.g., https://api.proofy.io)",
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

    # Feature options
    group.addoption(
        "--proofy-disable-attachments",
        action="store_true",
        help="Disable attachment processing",
    )
    group.addoption(
        "--proofy-disable-hooks",
        action="store_true",
        help="Disable plugin hook system",
    )

    # Performance options
    group.addoption(
        "--proofy-timeout",
        action="store",
        type=float,
        default=None,
        help="API request timeout in seconds",
    )
    group.addoption(
        "--proofy-max-retries",
        action="store",
        type=int,
        default=None,
        help="Maximum number of API retry attempts",
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
    return ProofyConfig(
        mode=get_option("proofy_mode", "PROOFY_MODE", "proofy_mode", "lazy"),
        api_base=get_option("proofy_api_base", "PROOFY_API_BASE", "proofy_api_base"),
        token=get_option("proofy_token", "PROOFY_TOKEN", "proofy_token"),
        project_id=get_option(
            "proofy_project_id", "PROOFY_PROJECT_ID", "proofy_project_id", type_func=int
        ),
        batch_size=get_option(
            "proofy_batch_size", "PROOFY_BATCH_SIZE", "proofy_batch_size", 10, int
        ),
        output_dir=get_option(
            "proofy_output_dir",
            "PROOFY_OUTPUT_DIR",
            "proofy_output_dir",
            "proofy-artifacts",
        ),
        always_backup=get_option(
            "proofy_always_backup",
            "PROOFY_ALWAYS_BACKUP",
            "proofy_always_backup",
            False,
            bool,
        ),
        run_id=get_option("proofy_run_id", "PROOFY_RUN_ID", "proofy_run_id", type_func=int),
        run_name=get_option("proofy_run_name", "PROOFY_RUN_NAME", "proofy_run_name"),
        enable_attachments=not get_option(
            "proofy_disable_attachments",
            "PROOFY_DISABLE_ATTACHMENTS",
            "proofy_disable_attachments",
            False,
            bool,
        ),
        enable_hooks=not get_option(
            "proofy_disable_hooks",
            "PROOFY_DISABLE_HOOKS",
            "proofy_disable_hooks",
            False,
            bool,
        ),
        timeout_s=get_option("proofy_timeout", "PROOFY_TIMEOUT", "proofy_timeout", 30.0, float),
        max_retries=get_option(
            "proofy_max_retries", "PROOFY_MAX_RETRIES", "proofy_max_retries", 3, int
        ),
    )


def setup_pytest_ini_options(parser: pytest.Parser) -> None:
    """Setup pytest.ini configuration options."""
    parser.addini("proofy_mode", "Proofy delivery mode", default="lazy")
    parser.addini("proofy_api_base", "Proofy API base URL")
    parser.addini("proofy_token", "Proofy API token")
    parser.addini("proofy_project_id", "Proofy project ID")
    parser.addini("proofy_batch_size", "Batch size for results", default="10")
    parser.addini("proofy_output_dir", "Output directory for backups", default="proofy-artifacts")
    parser.addini("proofy_always_backup", "Always create backup files", default="false")
    parser.addini("proofy_run_id", "Existing run ID")
    parser.addini("proofy_run_name", "Test run name")
    parser.addini("proofy_disable_attachments", "Disable attachments", default="false")
    parser.addini("proofy_disable_hooks", "Disable hooks", default="false")
    parser.addini("proofy_timeout", "API timeout in seconds", default="30.0")
    parser.addini("proofy_max_retries", "Maximum retry attempts", default="3")
