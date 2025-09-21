"""Data models for Proofy test results and related entities."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar

from proofy.utils import format_datetime_rfc3339


class RunStatus(int, Enum):
    """Status of a test run."""

    STARTED = 1
    FINISHED = 2
    ABORTED = 3
    TIMEOUT = 4


class ResultStatus(int, Enum):
    """Status of a test result."""

    PASSED = 1
    FAILED = 2
    BROKEN = 3
    SKIPPED = 4
    IN_PROGRESS = 5


class ReportingStatus(int, Enum):
    """Status of a test reporting."""

    NOT_STARTED = 0
    INITIALIZED = 1
    FINISHED = 2
    FAILED = -1


class ProofyAttributes(str, Enum):
    """Standard Proofy attribute names."""

    DESCRIPTION = "description"
    SEVERITY = "severity"
    TITLE = "title"


@dataclass
class Attachment:
    """Test attachment with file information."""

    name: str
    path: str
    mime_type: str | None = None
    size_bytes: int | None = None
    remote_id: str | None = None  # Server-assigned ID for uploaded attachments
    file_id: str | None = None  # Legacy compatibility with old project


@dataclass
class FixtureResult:
    """Result of test fixture execution."""

    name: str
    setup_ok: bool = True
    teardown_ok: bool = True
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    """Unified test result model."""

    __test__: ClassVar[bool] = False  # Prevent pytest from treating this as a test class

    id: str  # Local ID
    name: str  # Display name
    path: str  # Main proofy identifier
    test_path: str  # Test file path

    run_id: int | None = None  # Run ID
    result_id: int | None = None  # Server-generated ID for live mode and attachments

    outcome: str | None = None  # passed, failed, skipped, error
    status: ResultStatus | None = None  # Enum format

    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: float | None = None  # Milliseconds

    # Test context and metadata
    parameters: dict[str, Any] = field(default_factory=dict)
    markers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    # Error information
    message: str | None = None
    traceback: str | None = None
    stdout: str | None = None
    stderr: str | None = None

    # Related entities
    attachments: list[Attachment] = field(default_factory=list)
    fixtures: list[FixtureResult] = field(default_factory=list)

    reporting_status: ReportingStatus = ReportingStatus.NOT_STARTED

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with proper serialization."""

        def convert_value(val: Any) -> Any:
            if isinstance(val, datetime):
                format_datetime_rfc3339(val)
            elif isinstance(val, list):
                return [convert_value(v) for v in val]
            elif isinstance(val, dict):
                return {k: convert_value(v) for k, v in val.items()}
            elif isinstance(val, Enum):
                return val.value
            elif hasattr(val, "__dict__"):
                return convert_value(asdict(val))
            return val

        return {key: convert_value(value) for key, value in asdict(self).items()}

    @property
    def effective_outcome(self) -> str | None:
        """Get effective outcome, prioritizing outcome over status."""
        if self.outcome:
            return self.outcome
        if self.status:
            return {
                ResultStatus.PASSED: "passed",
                ResultStatus.FAILED: "failed",
                ResultStatus.BROKEN: "error",
                ResultStatus.SKIPPED: "skipped",
                ResultStatus.IN_PROGRESS: "running",
            }.get(self.status)
        return None

    @property
    def effective_duration_ms(self) -> int | None:
        """Get effective duration in milliseconds."""
        if self.duration_ms is not None:
            return int(self.duration_ms)
        if self.started_at and self.ended_at:
            delta = self.ended_at - self.started_at
            return int(delta.total_seconds() * 1000.0)
        return None

    def merge_metadata(self) -> dict[str, Any]:
        """Merge all metadata sources into unified dict."""
        merged = {}

        # Start with metadata
        merged.update(self.metadata)

        # Add attributes
        if self.attributes:
            merged.update(self.attributes)

        if self.tags:
            merged.update({"__proofy_tags": self.tags})

        return merged
