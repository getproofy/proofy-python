"""Hook specifications for the Proofy plugin system."""

from __future__ import annotations

from typing import Any

from pluggy import HookimplMarker, HookspecMarker

from ..core.models import TestResult

hookspec = HookspecMarker("proofy")
hookimpl = HookimplMarker("proofy")


class ProofyHookSpecs:
    """Hook specifications for Proofy framework integration."""

    # ========== Test Lifecycle Hooks ==========

    @hookspec
    def proofy_test_start(
        self,
        test_id: str,
        test_name: str,
        test_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Called when a test starts execution.

        Args:
            test_id: Unique identifier for the test (nodeid)
            test_name: Display name of the test
            test_path: Path to the test file
            metadata: Optional metadata dictionary
        """

    @hookspec
    def proofy_test_finish(self, test_result: TestResult) -> None:
        """Called when a test finishes execution.

        Args:
            test_result: Complete test result with outcome and timing
        """

    @hookspec
    def proofy_test_update(self, test_id: str, metadata: dict[str, Any]) -> None:
        """Called to update test metadata during execution.

        Args:
            test_id: Test identifier
            metadata: Metadata to update/merge
        """

    # ========== Session Lifecycle Hooks ==========

    @hookspec
    def proofy_session_start(
        self,
        session_id: str,
        run_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Called when test session starts.

        Args:
            session_id: Unique session identifier
            run_name: Optional name for the test run
            metadata: Optional session metadata
        """

    @hookspec
    def proofy_session_finish(
        self,
        session_id: str,
        results: list[TestResult],
        summary: dict[str, Any] | None = None,
    ) -> None:
        """Called when test session finishes.

        Args:
            session_id: Session identifier
            results: All test results from the session
            summary: Optional session summary statistics
        """

    # ========== Attachment Hooks ==========

    @hookspec
    def proofy_add_attachment(
        self,
        test_id: str | None,
        file_path: str,
        name: str,
        mime_type: str | None = None,
    ) -> None:
        """Called to add an attachment to the current test.

        Args:
            test_id: Test identifier (current test if None)
            file_path: Path to the attachment file
            name: Display name for the attachment
            mime_type: MIME type of the attachment
        """

    @hookspec
    def proofy_attachment_uploaded(
        self, test_id: str, attachment_name: str, remote_id: str
    ) -> None:
        """Called when an attachment is successfully uploaded.

        Args:
            test_id: Test identifier
            attachment_name: Name of the uploaded attachment
            remote_id: Server-assigned ID for the attachment
        """

    # ========== Metadata Hooks ==========

    @hookspec
    def proofy_add_attributes(self, test_id: str | None, attributes: dict[str, Any]) -> None:
        """Called to add attributes to a test.

        Args:
            test_id: Test identifier (current test if None)
            attributes: Attributes to add/merge
        """

    @hookspec
    def proofy_set_name(self, test_id: str | None, name: str) -> None:
        """Called to set/override test display name.

        Args:
            test_id: Test identifier (current test if None)
            name: New display name for the test
        """

    @hookspec
    def proofy_set_description(self, test_id: str | None, description: str) -> None:
        """Called to set test description.

        Args:
            test_id: Test identifier (current test if None)
            description: Test description
        """

    @hookspec
    def proofy_set_severity(self, test_id: str | None, severity: str) -> None:
        """Called to set test severity level.

        Args:
            test_id: Test identifier (current test if None)
            severity: Severity level (e.g., 'critical', 'high', 'medium', 'low')
        """

    @hookspec
    def proofy_add_tags(self, test_id: str | None, tags: list[str]) -> None:
        """Called to add tags to a test.

        Args:
            test_id: Test identifier (current test if None)
            tags: List of tags to add
        """

    # ========== Run Management Hooks ==========

    @hookspec
    def proofy_set_run_name(self, name: str) -> None:
        """Called to set/override the test run name.

        Args:
            name: New name for the test run
        """

    @hookspec
    def proofy_run_created(self, run_id: int, run_name: str) -> None:
        """Called when a test run is created on the server.

        Args:
            run_id: Server-assigned run ID
            run_name: Name of the created run
        """

    # ========== Framework Integration Hooks ==========

    @hookspec
    def proofy_configure(self, config: dict[str, Any]) -> None:
        """Called during framework configuration.

        Args:
            config: Configuration dictionary
        """

    @hookspec
    def proofy_collect_tests(self, collected_tests: list[dict[str, Any]]) -> None:
        """Called after test collection phase.

        Args:
            collected_tests: List of collected test information
        """

    # ========== Marker/Decorator Hooks ==========

    @hookspec
    def proofy_mark_attributes(self, attributes: dict[str, Any]) -> Any:
        """Called to create test markers with attributes.

        Args:
            attributes: Attributes for the marker

        Returns:
            Framework-specific marker/decorator object
        """

    @hookspec
    def proofy_apply_marker(
        self, test_id: str, marker_name: str, marker_args: dict[str, Any]
    ) -> None:
        """Called when a marker is applied to a test.

        Args:
            test_id: Test identifier
            marker_name: Name of the marker
            marker_args: Marker arguments/attributes
        """
