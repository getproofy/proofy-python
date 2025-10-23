"""Main pytest plugin for Proofy test reporting."""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from proofy._internal.config import ProofyConfig
from proofy._internal.constants import PredefinedAttribute
from proofy._internal.hooks import get_plugin_manager, hookimpl
from proofy._internal.hooks.manager import reset_plugin_manager
from proofy._internal.results import ResultsHandler

# Import from proofy-commons
from proofy.core.models import ReportingStatus, ResultStatus, RunStatus, TestResult
from proofy.core.utils import generate_test_identifier
from pytest import CallInfo

from .config import (
    register_options,
    resolve_options,
    setup_pytest_ini_options,
)

logger = logging.getLogger("ProofyPytestPlugin")


class ProofyPytestPlugin:
    """Main Proofy pytest plugin class."""

    def __init__(self, config: ProofyConfig, collect_only: bool):
        self.config = config
        self.run_id: int | None = None

        # Plugin state
        self._start_time: datetime | None = None
        self._num_deselected = 0
        self._terminal_summary = ""
        self._session_error_message: str | None = None
        self._had_collection_errors: bool = False
        self._collect_only: bool = collect_only

        # Initialize results handler
        self.results_handler = ResultsHandler(
            config=config,
            framework="pytest",
            disable_output=collect_only,
        )

    def _get_test_id(self, item: pytest.Item) -> str:
        """Generate consistent test ID from pytest item."""
        return (
            item.nodeid
        )  # TODO: create test id as uuid base on thread_id, item.nodeid and item rerun iteration

    def _get_test_name(self, item: pytest.Item) -> str:
        """Get display name for test."""
        # Use class name if available
        if hasattr(item, "cls") and item.cls and item.name:
            return f"{item.cls.__name__}::{item.name}"
        return item.name

    def _get_path(self, item: pytest.Item) -> str:
        """Generate consistent path from pytest item."""
        return item.nodeid

    def _get_test_path(self, item: pytest.Item) -> Path:
        """Get relative path for test."""
        try:
            root = getattr(item.config, "rootpath", None) or getattr(item.config, "rootdir", None)
            if root:
                return Path(item.fspath).relative_to(Path(root))
        except Exception:
            pass
        return Path(item.fspath)

    def _outcome_to_status(self, outcome: str) -> ResultStatus:
        """Convert pytest outcome to ResultStatus."""
        mapping = {
            "passed": ResultStatus.PASSED,
            "failed": ResultStatus.FAILED,
            "error": ResultStatus.BROKEN,
            "skipped": ResultStatus.SKIPPED,
        }
        return mapping.get(outcome, ResultStatus.BROKEN)

    def _get_attributes(self, item: pytest.Item) -> dict[str, Any]:
        attributes: dict[str, Any] = {}
        for mark in item.iter_markers(name="proofy_attributes"):
            attributes.update(
                {key: value for key, value in mark.kwargs.items() if key not in attributes}
            )
        return attributes

    def _get_markers(self, item: pytest.Item) -> list[str]:
        """Collect markers (excluding internal ones) as a list of strings with length limit.

        Format: ["name(arg1, arg2, key=value)"]
        Applies a JSON-length limit (default 100) and appends "..." if truncated.
        """
        try:
            all_marks = list(item.iter_markers())
        except Exception:
            all_marks = []

        formatted: list[str] = []

        for m in all_marks:
            name = getattr(m, "name", None)
            if not isinstance(name, str):
                continue
            if name in ("parametrize", "proofy_attributes", "skip"):
                continue
            if name.startswith("__proofy_"):
                continue

            args = [repr(a) for a in (getattr(m, "args", []) or [])]
            kwargs_items = (getattr(m, "kwargs", {}) or {}).items()
            kwargs = [f"{k}={repr(v)}" for k, v in kwargs_items]

            if not args and not kwargs:
                marker_str = name
            else:
                params = ", ".join(args + kwargs)
                marker_str = f"{name}({params})"

            formatted.append(marker_str)

        return formatted

    def _get_parameters(self, item: pytest.Item) -> dict[str, Any]:
        """Collect parameters with a JSON-length limit and truncation marker.

        Keeps the mapping shape but ensures the serialized JSON stays under the
        limit by stopping early and optionally appending an indicator key.
        """
        return getattr(getattr(item, "callspec", None), "params", {}) or {}

    def _get_test_identifier(self, item: pytest.Item) -> str:
        """Generate a unique test identifier.

        Converts pytest's nodeid format (e.g., "tests/test_file.py::TestClass::test_method")
        to a framework-agnostic 16-character identifier using SHA256 hashing.
        """
        return generate_test_identifier(item.nodeid)

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionstart(self, session: pytest.Session) -> None:
        """Called at the start of test session."""
        self.results_handler.start_session(
            run_id=self.config.run_id,
            config=self.config,
        )

        self.run_id = self.results_handler.start_run()
        self.config.run_id = self.run_id

        if not self.run_id and self.results_handler.client:
            logger.error("Run ID not found after start_run; proceeding without server sync.")

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item) -> Generator[None, None, None]:
        """Called before each test is executed."""
        self._start_time = datetime.now(timezone.utc)

        attributes = self._get_attributes(item)
        display_name = attributes.pop(PredefinedAttribute.NAME.value, None)

        result = TestResult(
            id=self._get_test_id(item),
            name=display_name or self._get_test_name(item),
            path=self._get_path(item),
            test_path=self._get_test_path(item).as_posix(),
            test_identifier=self._get_test_identifier(item),
            status=ResultStatus.IN_PROGRESS,
            started_at=self._start_time,
            run_id=self.run_id,
            attributes=attributes,
            parameters=self._get_parameters(item),
            markers=self._get_markers(item),
        )
        self.results_handler.on_test_started(result)
        yield

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(
        self, item: pytest.Item, call: CallInfo[None]
    ) -> Generator[None, None, None]:
        """Called to create test reports."""
        outcome = yield
        report = outcome.get_result()  # type: ignore[attr-defined]

        status = self._outcome_to_status(report.outcome)
        result: TestResult | None = self.results_handler.get_result(self._get_test_id(item))

        # Create result if not exists yet
        if not result:
            logger.error("Result not found for test %s", self._get_test_id(item))
            return

        excinfo = getattr(call, "excinfo", None)
        if report.failed and excinfo is not None:
            result.message = excinfo.exconly()
            # TODO: handle multiple lines in traceback, add report.when to traceback
            result.traceback = report.longreprtext

            if status != ResultStatus.SKIPPED and not isinstance(excinfo.value, AssertionError):
                status = ResultStatus.BROKEN

        # Capture skip reason/message when a test is skipped
        if status == ResultStatus.SKIPPED and not result.message:
            skip_message: str | None = None
            try:
                longrepr = getattr(report, "longrepr", None)
                if isinstance(longrepr, tuple | list) and len(longrepr) >= 3:
                    skip_message = str(longrepr[2])
                elif isinstance(longrepr, str) and longrepr:
                    skip_message = longrepr
                if not skip_message:
                    longreprtext = getattr(report, "longreprtext", None)
                    if isinstance(longreprtext, str) and longreprtext:
                        text = longreprtext.strip()
                        if text.lower().startswith("skipped"):
                            parts = text.split(":", 1)
                            skip_message = parts[1].strip() if len(parts) == 2 else text
                        else:
                            skip_message = text
                if not skip_message:
                    skip_excinfo = getattr(call, "excinfo", None)
                    if skip_excinfo is not None:
                        try:
                            skip_message = str(skip_excinfo.value)
                        except Exception:
                            skip_message = None
            except Exception:
                skip_message = None

            if skip_message:
                result.message = skip_message

        if report.when == "setup":
            result.status = status

        if report.when == "call" and result.status == ResultStatus.PASSED:
            result.status = status
            result.outcome = report.outcome

        if report.when == "teardown":
            end_time = datetime.now(timezone.utc)
            result.ended_at = end_time
            if result.started_at is not None:
                result.duration_ms = int((end_time - result.started_at).total_seconds() * 1000)
            if (
                status in (ResultStatus.FAILED, ResultStatus.BROKEN)
                and result.status == ResultStatus.PASSED
            ):
                result.status = status

            stdout = getattr(report, "capstdout", None)
            if stdout:
                result.stdout = stdout
            stderr = getattr(report, "capstderr", None)
            if stderr:
                result.stderr = stderr

            self.results_handler.on_test_finished(result=result)

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Called at the end of test session."""
        # Decide final run status
        final_status = RunStatus.FINISHED
        if exitstatus in {2, 3, 4} or self._had_collection_errors:
            final_status = RunStatus.ABORTED

        # Finalize run with possible error message attribute
        self.results_handler.finish_run(
            run_id=self.run_id,
            status=final_status,
            error_message=self._session_error_message,
        )

        # Backup results locally if configured
        if self.config.always_backup:
            self.results_handler.backup_results()

        try:
            results = self.results_handler.context.get_results()
            uploaded_ok = sum(
                1
                for r in results.values()
                if getattr(r, "reporting_status", None) == ReportingStatus.FINISHED
            )
        except Exception:
            uploaded_ok = 0

        self._terminal_summary += f"Uploaded {uploaded_ok} result(s) to Proofy\n"

        self.results_handler.end_session()

    def pytest_deselected(self, items: list[pytest.Item]) -> None:
        self._num_deselected += len(items)
        for item in items:
            json_collectitem = getattr(item, "_json_collectitem", None)
            if isinstance(json_collectitem, dict):
                json_collectitem["deselected"] = True

    @pytest.hookimpl(trylast=True)
    def pytest_terminal_summary(self, terminalreporter: pytest.TerminalReporter) -> None:
        terminalreporter.write_sep("-", "Proofy report")
        terminalreporter.write_line(str(self._terminal_summary))

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        """Capture collection errors to mark run as aborted and store message."""
        try:
            failed = getattr(report, "failed", False)
            if failed:
                self._had_collection_errors = True
                longreprtext = getattr(report, "longreprtext", None)
                longrepr = getattr(report, "longrepr", None)
                nodeid = getattr(report, "nodeid", None)
                msg = None
                if isinstance(longreprtext, str) and longreprtext:
                    msg = longreprtext
                elif longrepr is not None:
                    try:
                        msg = str(longrepr)
                    except Exception:
                        msg = None
                # Fallback concise message
                if not msg:
                    msg = f"Collection error at {nodeid or '<unknown>'}"
                # Persist a trimmed error to avoid huge payloads
                self._session_error_message = msg[:100]
        except Exception:
            pass


# Hook implementations for integration with proofy hook system
class PytestProofyHooks:
    """Hook implementations for pytest integration."""

    @hookimpl
    def proofy_test_start(self, test_id: str, test_name: str, test_path: str) -> None:
        """Called when test starts."""
        pass

    @hookimpl
    def proofy_test_finish(self, test_result: TestResult) -> None:
        """Called when test finishes."""
        pass

    @hookimpl
    def proofy_mark_attributes(self, attributes: dict[str, Any]) -> Any:
        """Create pytest mark for attributes."""
        return pytest.mark.proofy_attributes(**attributes)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add command line options."""
    register_options(parser)
    setup_pytest_ini_options(parser)


def pytest_configure(config: pytest.Config) -> None:
    pm = get_plugin_manager()

    config.addinivalue_line("markers", "proofy_attributes: proofy attributes markers")

    _proofy_hooks_instance = PytestProofyHooks()
    config._proofy_hooks = _proofy_hooks_instance  # type: ignore[attr-defined]
    pm.register(_proofy_hooks_instance, "pytest_proofy_hooks")

    collect_only = config.getoption("collectonly", False)
    proofy_config = resolve_options(config)

    if not proofy_config.enabled:
        return

    _plugin_instance = ProofyPytestPlugin(proofy_config, collect_only)
    config._proofy = _plugin_instance  # type: ignore[attr-defined]
    config.pluginmanager.register(_plugin_instance, "proofy_plugin")
    pm.register(_plugin_instance, "pytest_proofy")

    # Propagate mode and output dir to environment for proofy-commons caching logic
    try:
        if proofy_config.mode:
            os.environ.setdefault("PROOFY_MODE", proofy_config.mode)
        if proofy_config.output_dir:
            os.environ.setdefault("PROOFY_OUTPUT_DIR", proofy_config.output_dir)
        if proofy_config.batch_size:
            os.environ.setdefault("PROOFY_BATCH_SIZE", str(proofy_config.batch_size))
    except Exception:
        pass


def pytest_unconfigure(config: pytest.Config) -> None:
    plugin = getattr(config, "_proofy", None)
    if plugin is not None:
        del config._proofy  # type: ignore[attr-defined]
        config.pluginmanager.unregister(plugin, "proofy_plugin")
    hooks = getattr(config, "_proofy_hooks", None)
    if hooks is not None:
        del config._proofy_hooks  # type: ignore[attr-defined]
        reset_plugin_manager()
