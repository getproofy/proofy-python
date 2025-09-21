"""Core components for Proofy integration."""

from .client import ProofyClient
from .models import (
    Attachment,
    FixtureResult,
    ProofyAttributes,
    ResultStatus,
    RunStatus,
    TestResult,
)

__all__ = [
    "ProofyClient",
    "TestResult",
    "Attachment",
    "FixtureResult",
    "ResultStatus",
    "RunStatus",
    "ProofyAttributes",
]
