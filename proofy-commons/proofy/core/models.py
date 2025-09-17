"""Data models for Proofy test results and related entities."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar


class RunStatus(int, Enum):
    """Status of a test run."""

    STARTED = 1
    FINISHED = 2
    ABORTED = 3


class ResultStatus(int, Enum):
    """Status of a test result."""

    PASSED = 1
    FAILED = 2
    BROKEN = 3
    SKIPPED = 4
    IN_PROGRESS = 5


class ProofyAttributes(str, Enum):
    """Standard Proofy attribute names."""

    DESCRIPTION = "description"
    SEVERITY = "severity"
    TITLE = "title"


@dataclass
class Property:
    """A key-value property for test metadata."""

    key: str
    value: Any


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
    """Unified test result model combining both projects' approaches."""

    __test__: ClassVar[bool] = False  # Prevent pytest from treating this as a test class

    # Core identification (from current project)
    id: str  # Local ID (nodeid)
    name: str
    path: str

    # Server integration (from old project)
    run_id: int | None = None
    server_id: int | None = None  # Server-generated ID for live mode

    # Test execution details
    nodeid: str | None = None
    outcome: str | None = None  # passed, failed, skipped, error (current project format)
    status: ResultStatus | None = None  # Enum format (old project format)

    # Timing information
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_ms: float | None = None  # Milliseconds (current project)
    duration: int | None = None  # Milliseconds (old project, for compatibility)

    # Test context and metadata
    parameters: dict[str, Any] = field(default_factory=dict)
    markers: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)  # Old project format
    properties: list[Property] | None = None  # Old project format
    meta_data: dict[str, Any] | None = None  # Old project format

    # Error information
    error: str | None = None
    message: str | None = None  # Old project format
    traceback: str | None = None
    trace: str | None = None  # Old project format

    # Related entities
    attachments: list[Attachment] = field(default_factory=list)
    fixtures: list[FixtureResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with proper serialization."""

        def convert_value(val: Any) -> Any:
            if isinstance(val, datetime):
                return val.isoformat()
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
    def effective_duration_ms(self) -> float | None:
        """Get effective duration in milliseconds."""
        if self.duration_ms is not None:
            return self.duration_ms
        if self.duration is not None:
            return float(self.duration)
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() * 1000.0
        return None

    def merge_metadata(self) -> dict[str, Any]:
        """Merge all metadata sources into unified dict."""
        merged = {}

        # Start with metadata (current project)
        merged.update(self.metadata)

        # Add attributes (old project)
        if self.attributes:
            merged.update(self.attributes)

        # Add meta_data (old project)
        if self.meta_data:
            merged.update(self.meta_data)

        # Add properties (old project)
        if self.properties:
            for prop in self.properties:
                merged[prop.key] = prop.value

        return merged
