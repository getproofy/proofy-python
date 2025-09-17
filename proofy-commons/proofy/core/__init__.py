"""Core components for Proofy integration."""

from .client import ProofyClient
from .models import (
    Attachment,
    FixtureResult,
    ProofyAttributes,
    Property,
    ResultStatus,
    RunStatus,
    TestResult,
)

__all__ = [
    "ProofyClient",
    "TestResult",
    "Attachment",
    "FixtureResult",
    "Property",
    "ResultStatus",
    "RunStatus",
    "ProofyAttributes",
]
