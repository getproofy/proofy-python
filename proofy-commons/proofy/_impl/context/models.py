"""Internal context models for session and test state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from proofy._impl.config import ProofyConfig
from proofy.core.models import TestResult


@dataclass
class SessionContext:
    """Session-level state and registry of tests."""

    session_id: str
    run_id: int | None = None
    run_name: str | None = None
    config: ProofyConfig | dict[str, Any] | None = None
    test_results: dict[str, TestResult] = field(default_factory=dict)
    run_attributes: dict[str, Any] = field(default_factory=dict)
