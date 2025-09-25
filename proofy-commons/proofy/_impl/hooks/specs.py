"""Hook specifications for the Proofy plugin system."""

from __future__ import annotations

from typing import Any

from pluggy import HookimplMarker, HookspecMarker

from ...core.models import TestResult

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

    # ========== Marker/Decorator Hooks ==========

    @hookspec
    def proofy_mark_attributes(self, attributes: dict[str, Any]) -> Any:
        """Called to create test markers with attributes.

        Args:
            attributes: Attributes for the marker

        Returns:
            Framework-specific marker/decorator object
        """
