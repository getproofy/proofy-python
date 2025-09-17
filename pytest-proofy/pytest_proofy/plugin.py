"""Main pytest plugin for Proofy test reporting."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

import pytest
from _pytest.reports import TestReport

# Import from proofy-commons
from proofy import (
    Attachment,
    ProofyClient,
    ResultStatus,
    RunStatus,
    TestContext,
    TestResult,
    get_current_test_context,
    get_plugin_manager,
    hookimpl,
    set_current_test_context,
)

from .config import (
    ProofyConfig,
    register_options,
    resolve_options,
    setup_pytest_ini_options,
)


class ProofyPytestPlugin:
    """Main Proofy pytest plugin class."""

    def __init__(self, config: ProofyConfig):
        self.config = config
        self.client: ProofyClient | None = None
        self.run_id: int | None = None
        self.session_id = str(uuid.uuid4())
        self.test_results: dict[str, TestResult] = {}
        self.test_start_times: dict[str, datetime] = {}

        # Initialize client if API configured
        if config.api_base and config.token:
            self.client = ProofyClient(
                base_url=config.api_base, token=config.token, timeout_s=config.timeout_s
            )

        # Register with hook system if enabled
        if config.enable_hooks:
            pm = get_plugin_manager()
            from contextlib import suppress

            with suppress(ValueError):
                # Plugin already registered (e.g., during testing)
                pm.register(self, "pytest_proofy")

    def _get_test_id(self, item: pytest.Item) -> str:
        """Generate consistent test ID from pytest item."""
        return item.nodeid

    def _get_test_name(self, item: pytest.Item) -> str:
        """Get display name for test."""
        # Check if test context has custom name
        ctx = get_current_test_context()
        if ctx and ctx.name:
            return ctx.name

        # Use item name with class if available
        if hasattr(item, "cls") and item.cls:
            return f"{item.cls.__name__}::{item.name}"
        return item.name

    def _get_test_path(self, item: pytest.Item) -> str:
        """Get relative path for test."""
        try:
            root = getattr(item.config, "rootpath", None) or getattr(item.config, "rootdir", None)
            if root:
                return str(Path(item.fspath).relative_to(Path(str(root))))
        except Exception:
            pass
        return str(item.fspath)

    def _outcome_to_status(self, outcome: str) -> ResultStatus:
        """Convert pytest outcome to ResultStatus."""
        mapping = {
            "passed": ResultStatus.PASSED,
            "failed": ResultStatus.FAILED,
            "error": ResultStatus.BROKEN,
            "skipped": ResultStatus.SKIPPED,
        }
        return mapping.get(outcome, ResultStatus.BROKEN)

    def _create_test_result(self, item: pytest.Item, report: TestReport) -> TestResult:
        """Create TestResult from pytest item and report."""
        test_id = self._get_test_id(item)
        start_time = self.test_start_times.get(test_id, datetime.now())

        # Get context data
        ctx = get_current_test_context()

        # Calculate duration
        duration_ms = report.duration * 1000 if hasattr(report, "duration") else None

        # Create result
        result = TestResult(
            id=test_id,
            name=self._get_test_name(item),
            path=self._get_test_path(item),
            nodeid=item.nodeid,
            outcome=report.outcome,
            status=self._outcome_to_status(report.outcome),
            start_time=start_time,
            end_time=datetime.now(),
            duration_ms=duration_ms,
            run_id=self.run_id,
        )

        # Add context data if available
        if ctx:
            if ctx.description:
                result.metadata["description"] = ctx.description
            if ctx.severity:
                result.metadata["severity"] = ctx.severity
            if ctx.tags:
                result.tags.extend(ctx.tags)
            if ctx.metadata:
                result.metadata.update(ctx.metadata)
            if ctx.attributes:
                result.attributes.update(ctx.attributes)
            if ctx.files:
                for file_info in ctx.files:
                    attachment = Attachment(
                        name=file_info["name"],
                        path=file_info["path"],
                        mime_type=file_info.get("mime_type"),
                    )
                    result.attachments.append(attachment)

        # Add error information
        if report.failed and hasattr(report, "longrepr") and report.longrepr:
            result.error = str(report.longrepr)
            result.traceback = str(report.longrepr)

        # Add markers as tags
        for marker in item.iter_markers():
            if marker.name not in result.tags:
                result.tags.append(marker.name)

        return result

    def _send_result_live(self, result: TestResult) -> None:
        """Send result in live mode (create -> update pattern)."""
        if not self.client or not self.run_id:
            return

        try:
            # Create result at test start (if not already created)
            if not result.server_id:
                server_id = self.client.create_test_result(
                    run_id=self.run_id,
                    display_name=result.name,
                    path=result.path,
                    status=ResultStatus.IN_PROGRESS,
                    start_time=result.start_time or datetime.now(),
                    end_time=result.start_time or datetime.now(),  # Will be updated
                    duration=0,  # Will be updated
                    attributes=result.merge_metadata(),
                )
                result.server_id = server_id
                self.test_results[result.id] = result

            # Update result at test end
            if result.outcome:
                self.client.update_test_result(
                    result_id=result.server_id,
                    status=result.status or ResultStatus.BROKEN,
                    end_time=result.end_time or datetime.now(),
                    duration=int(result.effective_duration_ms or 0),
                    message=result.error,
                    trace=result.traceback,
                    attributes=result.merge_metadata(),
                )

                # Send attachments
                for attachment in result.attachments:
                    try:
                        self.client.add_attachment(
                            result_id=result.server_id,
                            file_name=attachment.name,
                            file=attachment.path,
                            content_type=attachment.mime_type or "application/octet-stream",
                        )
                    except Exception as e:
                        print(f"Failed to upload attachment {attachment.name}: {e}")

        except Exception as e:
            print(f"Failed to send result in live mode: {e}")

    def _send_result_lazy(self, result: TestResult) -> None:
        """Send result in lazy mode (send complete result)."""
        if not self.client:
            return

        try:
            self.client.send_test_result(result)
        except Exception as e:
            print(f"Failed to send result in lazy mode: {e}")

    def _create_run(self, session: pytest.Session) -> int | None:
        """Create a new test run."""
        if not self.client or not self.config.project_id:
            return None

        try:
            run_name = self.config.run_name or f"pytest-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

            response = self.client.create_test_run(
                project=self.config.project_id,
                name=run_name,
                status=RunStatus.STARTED,
                attributes={
                    "framework": "pytest",
                    "session_id": self.session_id,
                },
            )
            return response.get("id")
        except Exception as e:
            print(f"Failed to create run: {e}")
            return None

    def _finalize_run(self) -> None:
        """Finalize the test run."""
        if not self.client or not self.run_id:
            return

        try:
            self.client.update_test_run(
                run_id=self.run_id,
                status=RunStatus.FINISHED,
                end_time=datetime.now(),
                attributes={
                    "total_results": len(self.test_results),
                },
            )
        except Exception as e:
            print(f"Failed to finalize run: {e}")


# Plugin instance (will be set during configuration)
_plugin_instance: ProofyPytestPlugin | None = None


# Pytest hooks
def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command line options."""
    register_options(parser)
    setup_pytest_ini_options(parser)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Configure the plugin."""
    global _plugin_instance

    proofy_config = resolve_options(config)
    _plugin_instance = ProofyPytestPlugin(proofy_config)

    # Store plugin instance in config for access
    config._proofy_plugin = _plugin_instance  # type: ignore[attr-defined]


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    """Called at the start of test session."""
    if not _plugin_instance:
        return

    # Create run if using live or batch mode
    if _plugin_instance.config.mode in ("live", "batch"):
        if not _plugin_instance.config.run_id:
            _plugin_instance.run_id = _plugin_instance._create_run(session)
        else:
            _plugin_instance.run_id = _plugin_instance.config.run_id


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_setup(item: pytest.Item) -> None:
    """Called before each test is executed."""
    if not _plugin_instance:
        return

    test_id = _plugin_instance._get_test_id(item)
    _plugin_instance.test_start_times[test_id] = datetime.now()

    # Set up test context
    ctx = TestContext(test_id=test_id)
    set_current_test_context(ctx)

    # For live mode, create result immediately
    if (
        _plugin_instance.config.mode == "live"
        and _plugin_instance.client
        and _plugin_instance.run_id
    ):
        try:
            result = TestResult(
                id=test_id,
                name=_plugin_instance._get_test_name(item),
                path=_plugin_instance._get_test_path(item),
                nodeid=item.nodeid,
                status=ResultStatus.IN_PROGRESS,
                start_time=datetime.now(),
                run_id=_plugin_instance.run_id,
            )

            server_id = _plugin_instance.client.create_test_result(
                run_id=_plugin_instance.run_id,
                display_name=result.name,
                path=result.path,
                status=ResultStatus.IN_PROGRESS,
                start_time=result.start_time,
                end_time=result.start_time,
                duration=0,
            )
            result.server_id = server_id
            _plugin_instance.test_results[test_id] = result

        except Exception as e:
            print(f"Failed to create result for live mode: {e}")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Called to create test reports."""
    outcome = yield
    report = outcome.get_result()

    if not _plugin_instance or call.when != "call":
        return

    # Create and process test result
    result = _plugin_instance._create_test_result(item, report)
    test_id = _plugin_instance._get_test_id(item)

    # Update stored result or create new one
    if test_id in _plugin_instance.test_results:
        stored_result = _plugin_instance.test_results[test_id]
        # Update with report data
        stored_result.outcome = result.outcome
        stored_result.status = result.status
        stored_result.end_time = result.end_time
        stored_result.duration_ms = result.duration_ms
        stored_result.error = result.error
        stored_result.traceback = result.traceback
        result = stored_result
    else:
        _plugin_instance.test_results[test_id] = result

    # Send result based on mode
    if _plugin_instance.config.mode == "live":
        _plugin_instance._send_result_live(result)
    elif _plugin_instance.config.mode == "lazy":
        _plugin_instance._send_result_lazy(result)
    # Batch mode will be handled in session finish


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: pytest.Item) -> None:
    """Called after each test teardown."""
    # Clear test context
    set_current_test_context(None)


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Called at the end of test session."""
    if not _plugin_instance:
        return

    # Handle batch mode - send all results
    if _plugin_instance.config.mode == "batch" and _plugin_instance.client:
        try:
            results = list(_plugin_instance.test_results.values())
            if results:
                _plugin_instance.client.send_test_results(results)
        except Exception as e:
            print(f"Failed to send batch results: {e}")

    # Finalize run
    _plugin_instance._finalize_run()

    # Backup results locally if configured
    if _plugin_instance.config.always_backup or not _plugin_instance.client:
        _backup_results_locally(_plugin_instance)


def _backup_results_locally(plugin: ProofyPytestPlugin) -> None:
    """Create local backup of results."""
    try:
        import json
        from pathlib import Path

        output_dir = Path(plugin.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Export results as JSON
        results_data = [result.to_dict() for result in plugin.test_results.values()]

        results_file = output_dir / "results.json"
        with open(results_file, "w") as f:
            json.dump(results_data, f, indent=2, default=str)

        print(f"Results backed up to {results_file}")

    except Exception as e:
        print(f"Failed to backup results locally: {e}")


# Hook implementations for integration with proofy hook system
class PytestProofyHooks:
    """Hook implementations for pytest integration."""

    @hookimpl
    def proofy_test_start(self, test_id: str, test_name: str, test_path: str):
        """Called when test starts."""
        pass  # Already handled in pytest_runtest_setup

    @hookimpl
    def proofy_test_finish(self, test_result):
        """Called when test finishes."""
        pass  # Already handled in pytest_runtest_makereport

    @hookimpl
    def proofy_add_attachment(self, test_id: str, file_path: str, name: str, mime_type=None):
        """Called to add attachment."""
        if _plugin_instance and test_id in _plugin_instance.test_results:
            result = _plugin_instance.test_results[test_id]
            attachment = Attachment(
                name=name,
                path=file_path,
                mime_type=mime_type,
            )
            result.attachments.append(attachment)

    @hookimpl
    def proofy_mark_attributes(self, attributes):
        """Create pytest mark for attributes."""
        return pytest.mark.proofy_attributes(**attributes)
