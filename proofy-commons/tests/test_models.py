"""Tests for Proofy core models."""

from datetime import datetime

from proofy.core.models import Attachment, ResultStatus, RunStatus, TestResult


class TestTestResult:
    """Tests for TestResult model."""

    def test_basic_creation(self):
        """Test basic TestResult creation."""
        result = TestResult(id="test_example", name="Example Test", path="/tests/test_example.py")

        assert result.id == "test_example"
        assert result.name == "Example Test"
        assert result.path == "/tests/test_example.py"
        assert result.server_id is None
        assert result.outcome is None
        assert result.status is None

    def test_effective_outcome(self):
        """Test effective_outcome property."""
        # Test outcome priority
        result = TestResult(
            id="test1",
            name="Test 1",
            path="/test1.py",
            outcome="passed",
            status=ResultStatus.FAILED,
        )
        assert result.effective_outcome == "passed"

        # Test status fallback
        result = TestResult(id="test2", name="Test 2", path="/test2.py", status=ResultStatus.FAILED)
        assert result.effective_outcome == "failed"

        # Test no outcome or status
        result = TestResult(id="test3", name="Test 3", path="/test3.py")
        assert result.effective_outcome is None

    def test_effective_duration_ms(self):
        """Test effective_duration_ms property."""
        # Test duration_ms priority
        result = TestResult(
            id="test1",
            name="Test 1",
            path="/test1.py",
            duration_ms=1500.0,
        )
        assert result.effective_duration_ms == 1500.0

        # Test calculated from timestamps
        start = datetime(2023, 1, 1, 12, 0, 0)
        end = datetime(2023, 1, 1, 12, 0, 1, 500000)  # +1.5 seconds
        result = TestResult(
            id="test3", name="Test 3", path="/test3.py", started_at=start, ended_at=end
        )
        assert result.effective_duration_ms == 1500.0

    def test_merge_metadata(self):
        """Test merge_metadata method."""
        result = TestResult(
            id="test1",
            name="Test 1",
            path="/test1.py",
            metadata={"key1": "value1"},
            attributes={"key2": "value2"},
        )

        merged = result.merge_metadata()
        assert merged["key1"] == "value1"
        assert merged["key2"] == "value2"

    def test_to_dict(self):
        """Test to_dict serialization."""
        started_at = datetime(2023, 1, 1, 12, 0, 0)

        result = TestResult(
            id="test1",
            name="Test 1",
            path="/test1.py",
            outcome="passed",
            status=ResultStatus.PASSED,
            started_at=started_at,
            metadata={"key": "value"},
        )

        data = result.to_dict()

        assert data["id"] == "test1"
        assert data["name"] == "Test 1"
        assert data["outcome"] == "passed"
        assert data["status"] == 1  # ResultStatus.PASSED.value
        assert data["started_at"] == started_at.isoformat() + "Z"  # RFC 3339 format
        assert data["metadata"]["key"] == "value"


class TestAttachment:
    """Tests for Attachment model."""

    def test_basic_creation(self):
        """Test basic Attachment creation."""
        attachment = Attachment(
            name="screenshot", path="/tmp/screenshot.png", mime_type="image/png"
        )

        assert attachment.name == "screenshot"
        assert attachment.path == "/tmp/screenshot.png"
        assert attachment.mime_type == "image/png"
        assert attachment.remote_id is None
        assert attachment.file_id is None


class TestResultStatus:
    """Tests for ResultStatus enum."""

    def test_enum_values(self):
        """Test enum values match expected integers."""
        assert ResultStatus.PASSED.value == 1
        assert ResultStatus.FAILED.value == 2
        assert ResultStatus.BROKEN.value == 3
        assert ResultStatus.SKIPPED.value == 4
        assert ResultStatus.IN_PROGRESS.value == 5


class TestRunStatus:
    """Tests for RunStatus enum."""

    def test_enum_values(self):
        """Test enum values match expected integers."""
        assert RunStatus.STARTED.value == 1
        assert RunStatus.FINISHED.value == 2
        assert RunStatus.ABORTED.value == 3
        assert RunStatus.TIMEOUT.value == 4
