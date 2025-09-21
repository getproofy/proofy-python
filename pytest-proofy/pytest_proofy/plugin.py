"""Main pytest plugin for Proofy test reporting."""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from _pytest.reports import TestReport

# Import from proofy-commons
from proofy import (
    ProofyClient,
    ResultStatus,
    TestResult,
    get_plugin_manager,
    hookimpl,
)
from proofy._impl.io.results_handler import ResultsHandler
from proofy.export.attachments import (
    clear_attachments_cache,
)
from proofy.hooks.manager import reset_plugin_manager
from pytest import CallInfo

from .config import (
    ProofyConfig,
    register_options,
    resolve_options,
    setup_pytest_ini_options,
)
from .xdist_support import (
    is_xdist_worker,
    register_xdist_hooks,
    setup_worker_plugin,
    unregister_xdist_hooks,
)


class ProofyPytestPlugin:
    """Main Proofy pytest plugin class."""

    def __init__(self, config: ProofyConfig):
        self.config = config
        self.client: ProofyClient | None = None
        self.run_id: int | None = None
        # Results handler will be initialized after client is created
        self.results_handler: ResultsHandler | None = None
        self._start_time: datetime | None = None
        self._num_deselected = 0
        self._terminal_summary = ""

        # Initialize client if API configured
        if config.api_base and config.token:
            self.client = ProofyClient(
                base_url=config.api_base, token=config.token, timeout_s=config.timeout_s
            )

        # Initialize results handler (works without client as well)
        self.results_handler = ResultsHandler(
            client=self.client,
            mode=config.mode,
            output_dir=config.output_dir,
            project_id=config.project_id,
        )

    def _get_test_id(self, item: pytest.Item) -> str:
        """Generate consistent test ID from pytest item."""
        return (
            item.nodeid
        )  # create test id as uuid base on thread_id, item.nodeid and item rerun iteration

    def _get_test_name(self, item: pytest.Item) -> str:
        """Get display name for test."""
        self._get_attributes(item)
        name = self._get_attributes(item).get("proofy_name", item.name)

        # Use class name if available
        if hasattr(item, "cls") and item.cls and name:
            return f"{item.cls.__name__}::{name}"
        return name

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

    @pytest.hookimpl(tryfirst=True)
    def pytest_sessionstart(self, session: pytest.Session) -> None:
        """Called at the start of test session."""

        # Handle xdist worker initialization
        if is_xdist_worker(session):
            self = setup_worker_plugin(session)
        if not self:
            return

        # Clear attachments cache before starting tests (only on master, not workers)
        if not is_xdist_worker(session):
            clear_attachments_cache(self.config.output_dir)

        # Create/Update run only on master
        if not is_xdist_worker(session):  # Only on master
            self.run_id = self.results_handler.on_run_start(
                framework="pytest",
                run_name=self.config.run_name,
                run_id=self.config.run_id,
            )
            self.config.run_id = self.run_id  # type: ignore[attr-defined]
        else:
            if not self.config.run_id:
                raise RuntimeError(
                    "Run ID not found in config for worker process. Make sure to call on_run_start() first."
                )
            self.run_id = self.config.run_id  # type: ignore[attr-defined]

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item: pytest.Item):
        """Called before each test is executed."""

        self._start_time = datetime.now(timezone.utc)

        attributes = self._get_attributes(item)
        tags = attributes.get("proofy_tags", [])
        if tags:
            del attributes["proofy_tags"]

        if hasattr(item, "callspec"):
            parameters = item.callspec.params
        else:
            parameters = {}

        result = TestResult(
            id=self._get_test_id(item),
            name=self._get_test_name(item),
            path=self._get_path(item),
            test_path=self._get_test_path(item).as_posix(),
            status=ResultStatus.IN_PROGRESS,
            started_at=self._start_time,
            run_id=self.run_id,
            attributes=attributes,
            tags=tags,
            parameters=parameters,
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

        status_mapper = {
            "passed": ResultStatus.PASSED,
            "failed": ResultStatus.FAILED,
            "skipped": ResultStatus.SKIPPED,
        }
        status = status_mapper.get(report.outcome, ResultStatus.BROKEN)
        result: TestResult | None = self.results_handler.get_result(self._get_test_id(item))

        # Create result if not exists yet
        if not result:
            raise RuntimeError(f"Result for test {self._get_test_id(item)} not found")
            attributes = self._get_attributes(item)
            tags = attributes.get("proofy_tags", [])
            del attributes["proofy_tags"]

            if hasattr(item, "callspec"):
                parameters = item.callspec.params
            else:
                parameters = {}

            result = TestResult(
                id=self._get_test_id(item),
                name=self._get_test_name(item),
                path=self._get_path(item),
                test_path=self._get_test_path(item).as_posix(),
                status=ResultStatus.IN_PROGRESS,
                started_at=self._start_time or datetime.fromtimestamp(report.stop, timezone.utc),
                attributes=attributes,
                tags=tags,
                parameters=parameters,
            )
            self.results_handler.context.start_test(result)

        if report.failed and getattr(call, "excinfo", None) is not None:
            result.message = call.excinfo.exconly()
            result.traceback = report.longreprtext

            if status != ResultStatus.SKIPPED and not isinstance(
                call.excinfo.value, AssertionError
            ):
                status = ResultStatus.BROKEN

        if report.when == "setup":
            result.status = status

        if report.when == "call":
            if result.status == ResultStatus.PASSED:
                result.status = status

        if report.when == "teardown":
            end_time = datetime.now(timezone.utc)
            result.ended_at = end_time
            result.duration_ms = int((end_time - result.started_at).total_seconds() * 1000)
            if (
                status in (ResultStatus.FAILED, ResultStatus.BROKEN)
                and result.status == ResultStatus.PASSED
            ):
                result.status = status

            if stdout := report.capstdout:
                result.stdout = stdout
            if stderr := report.capstderr:
                result.stderr = stderr

            self.results_handler.on_test_finished(result=result)

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Called at the end of test session."""
        # In xdist workers, don't finalize run - only send results
        is_worker = is_xdist_worker(session)

        if is_xdist_worker(session):
            self.results_handler.flush_results()

        # Only finalize run on master process, not workers
        if not is_worker:
            self.results_handler.on_run_finish(run_id=self.run_id)

        # Backup results locally if configured
        if self.config.always_backup:
            self.results_handler.backup_results()
            if not is_worker:
                self.results_handler.merge_worker_results()

        self.results_handler.context.end_session()

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
        raise RuntimeError("PROOFY MARK ATTRIBUTES SHOULD NOT BE CALLED")
        return pytest.mark.proofy_attributes(**attributes)


# Pytest hooks
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

    # from contextlib import suppress

    # with suppress(ValueError):
    #     # Plugin already registered (e.g., during testing)
    #     pm.register(_plugin_instance, "pytest_proofy")

    # with suppress(ValueError):
    # # Plugin already registered (e.g., during testing)
    # pm.register(_plugin_instance, "pytest_proofy")

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
    except Exception:
        pass

    # Register xdist hooks if available
    register_xdist_hooks(config.pluginmanager, _plugin_instance)


# TODO: remove this once we have a better way to configure the plugin
# @pytest.hookimpl(tryfirst=True)
# def pytest_configure(config: pytest.Config) -> None:
#     """Configure the plugin."""
#     global _plugin_instance

#     proofy_config = resolve_options(config)
#     _plugin_instance = ProofyPytestPlugin(proofy_config)

#     # Add proofy attributes marker
#     config.addinivalue_line("markers", "proofy_attributes: proofy attributes markers")

#     # Propagate mode and output dir to environment for proofy-commons caching logic
#     try:
#         if proofy_config.mode:
#             os.environ.setdefault("PROOFY_MODE", proofy_config.mode)
#         if proofy_config.output_dir:
#             os.environ.setdefault("PROOFY_OUTPUT_DIR", proofy_config.output_dir)
#     except Exception:
#         pass

# # Store plugin instance in config for access
# config._proofy_plugin = _plugin_instance  # type: ignore[attr-defined]

# # Register xdist hooks if available
# register_xdist_hooks(config.pluginmanager, _plugin_instance)


def pytest_unconfigure(config: pytest.Config) -> None:
    plugin = getattr(config, "_proofy", None)
    if plugin is not None:
        del config._proofy
        config.pluginmanager.unregister(plugin, "proofy_plugin")
        unregister_xdist_hooks(config.pluginmanager)
    hooks = getattr(config, "_proofy_hooks", None)
    if hooks is not None:
        del config._proofy_hooks
        reset_plugin_manager()
