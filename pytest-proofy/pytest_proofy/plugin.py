"""Main pytest plugin for Proofy test reporting."""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from _pytest.reports import TestReport
from proofy._internal.config import ProofyConfig
from proofy._internal.hooks import get_plugin_manager, hookimpl
from proofy._internal.hooks.manager import reset_plugin_manager
from proofy._internal.results import ResultsHandler

# Import from proofy-commons
from proofy.core.models import ResultStatus, RunStatus, TestResult
from pytest import CallInfo

from .config import (
    register_options,
    resolve_options,
    setup_pytest_ini_options,
)


class ProofyPytestPlugin:
    """Main Proofy pytest plugin class."""

    def __init__(self, config: ProofyConfig):
        self.config = config
        self.run_id: int | None = None

        # Plugin state
        self._start_time: datetime | None = None
        self._num_deselected = 0
        self._terminal_summary = ""
        self._session_error_message: str | None = None
        self._had_collection_errors: bool = False

        # Initialize results handler
        self.results_handler = ResultsHandler(
            config=config,
            framework="pytest",
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

    def _get_attributes(self, item: pytest.Item) -> dict:
        attributes = {}
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
        limit = 100
        try:
            all_marks = list(item.iter_markers())
        except Exception:
            all_marks = []

        formatted: list[str] = []
        truncated = False

        for m in all_marks:
            name = getattr(m, "name", None)
            if not isinstance(name, str):
                continue
            if name == "parametrize":
                continue
            if name.startswith("__proofy_"):
                continue
            if name == "proofy_attributes":
                continue

            args = [repr(a) for a in (getattr(m, "args", []) or [])]
            kwargs_items = (getattr(m, "kwargs", {}) or {}).items()
            kwargs = [f"{k}={repr(v)}" for k, v in kwargs_items]
            params = ", ".join(args + kwargs)
            marker_str = f"{name}({params})"

            test_list = formatted + [marker_str]
            test_json = json.dumps(test_list, ensure_ascii=False)
            if len(test_json) <= limit:
                formatted.append(marker_str)
            else:
                truncated = True
                break

        if truncated:
            test_list = formatted + ["..."]
            test_json = json.dumps(test_list, ensure_ascii=False)
            if len(test_json) <= limit:
                formatted.append("...")

        return formatted

    def _get_parameters(self, item: pytest.Item) -> dict[str, Any]:
        """Collect parameters with a JSON-length limit and truncation marker.

        Keeps the mapping shape but ensures the serialized JSON stays under the
        limit by stopping early and optionally appending an indicator key.
        """
        limit = 100
        raw_params = getattr(getattr(item, "callspec", None), "params", {}) or {}
        parameters: dict[str, Any] = {}
        truncated_params = False
        try:
            for param_key, param_value in raw_params.items():
                candidate_value = param_value
                try:
                    json.dumps(candidate_value, ensure_ascii=False)
                except Exception:
                    candidate_value = repr(param_value)

                candidate_parameters = dict(parameters)
                candidate_parameters[param_key] = candidate_value
                if len(json.dumps(candidate_parameters, ensure_ascii=False)) <= limit:
                    parameters = candidate_parameters
                else:
                    truncated_params = True
                    break

            if truncated_params:
                candidate_parameters = dict(parameters)
                ellipsis_key = "..."
                if ellipsis_key in candidate_parameters:
                    ellipsis_key = "__truncated__"
                candidate_parameters[ellipsis_key] = True
                if len(json.dumps(candidate_parameters, ensure_ascii=False)) <= limit:
                    parameters = candidate_parameters
        except Exception:
            parameters = {}

        return parameters

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionstart(self, session: pytest.Session) -> None:
        """Called at the start of test session."""
        self.results_handler.start_session(
            run_id=self.config.run_id,
            config=self.config,
        )

        self.run_id = self.results_handler.start_run()
        self.config.run_id = self.run_id  # type: ignore[attr-defined]

        if not self.run_id and self.results_handler.client:
            raise RuntimeError("Run ID not found. Make sure to call start_run() first.")

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item):
        """Called before each test is executed."""
        self._start_time = datetime.now(timezone.utc)

        attributes = self._get_attributes(item)
        tags = attributes.pop("__proofy_tags", [])
        display_name = attributes.pop("__proofy_name", None)

        result = TestResult(
            id=self._get_test_id(item),
            name=display_name or self._get_test_name(item),
            path=self._get_path(item),
            test_path=self._get_test_path(item).as_posix(),
            status=ResultStatus.IN_PROGRESS,
            started_at=self._start_time,
            run_id=self.run_id,
            attributes=attributes,
            tags=tags,
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
        report: TestReport = outcome.get_result()  # type: ignore[attr-defined]

        status = self._outcome_to_status(report.outcome)
        result: TestResult | None = self.results_handler.get_result(self._get_test_id(item))

        # Create result if not exists yet
        if not result:
            raise RuntimeError(f"Result not found for test {self._get_test_id(item)}")

        if report.failed and getattr(call, "excinfo", None) is not None:
            result.message = call.excinfo.exconly()
            # TODO: handle multiple lines in traceback, add report.when to traceback
            result.traceback = report.longreprtext

            if status != ResultStatus.SKIPPED and not isinstance(
                call.excinfo.value, AssertionError
            ):
                status = ResultStatus.BROKEN

        if report.when == "setup":
            result.status = status

        if report.when == "call" and result.status == ResultStatus.PASSED:
            result.status = status
            result.outcome = report.outcome

        if report.when == "teardown":
            end_time = datetime.now(timezone.utc)
            result.ended_at = end_time
            result.duration_ms = int((end_time - result.started_at).total_seconds() * 1000)
            if (
                status in (ResultStatus.FAILED, ResultStatus.BROKEN)
                and result.status == ResultStatus.PASSED
            ):
                result.status = status

            if stdout := report.capstdout:  # type: ignore[attr-defined]
                result.stdout = stdout
            if stderr := report.capstderr:
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

        self.results_handler.end_session()

    def pytest_deselected(self, items: list[pytest.Item]) -> None:
        self._num_deselected += len(items)
        for item in items:
            try:
                item._json_collectitem["deselected"] = True  # type: ignore[attr-defined]
            except AttributeError:
                continue

    @pytest.hookimpl(trylast=True)
    def pytest_terminal_summary(self, terminalreporter):
        terminalreporter.write_sep("-", "Proofy report")
        terminalreporter.write_line(str(self._terminal_summary))

    def pytest_collectreport(self, report):
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
    config._proofy_hooks = _proofy_hooks_instance
    pm.register(_proofy_hooks_instance, "pytest_proofy_hooks")

    proofy_config = resolve_options(config)

    _plugin_instance = ProofyPytestPlugin(proofy_config)
    config._proofy = _plugin_instance
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
        del config._proofy
        config.pluginmanager.unregister(plugin, "proofy_plugin")
    hooks = getattr(config, "_proofy_hooks", None)
    if hooks is not None:
        del config._proofy_hooks
        reset_plugin_manager()
