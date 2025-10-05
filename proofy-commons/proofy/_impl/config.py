"""Shared configuration models for Proofy integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Mode = Literal["live", "batch", "lazy"]


@dataclass
class ProofyConfig:
    """Configuration for Proofy integrations and plugins.

    This dataclass is framework-agnostic and intended to be reused by
    integrations like pytest, behave, nose2, and unittest.
    """

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

    # Cache settings
    cache_attachments: bool = True

    # Run settings
    run_id: int | None = None
    run_name: str | None = None
    run_attributes: dict[str, str] | None = None

    # Feature flags
    enable_attachments: bool = True
    enable_hooks: bool = True

    # Timeout settings
    timeout_s: float = 30.0

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0


__all__ = [
    "Mode",
    "ProofyConfig",
]
