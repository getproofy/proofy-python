from __future__ import annotations

import json
from pathlib import Path

import pytest

# enable pytester fixture
pytest_plugins = ["pytester"]


def _load_results(base: Path, rel_dir: str = "proofy-artifacts") -> dict:
    results_path = base / rel_dir / "results.json"
    assert results_path.exists(), f"Results file not found at {results_path}"
    return json.loads(results_path.read_text())


def test_backup_and_metadata_with_marks(pytester: pytest.Pytester) -> None:
    # Optional: define custom marker used below to avoid warnings in some configs
    pytester.makeini(
        """
        [pytest]
        markers =
            slow: mark tests as slow
        """
    )

    pytester.makepyfile(
        test_sample="""
        import pytest

        @pytest.mark.proofy_attributes(team="A", __proofy_display_name="My Special Name")
        @pytest.mark.slow
        def test_pass():
            assert True

        def test_fail():
            assert 0

        def test_skip():
            pytest.skip("because we want to")
        """
    )

    result = pytester.runpytest("--proofy", "--proofy-backup")
    result.assert_outcomes(passed=1, failed=1, skipped=1)
    result.stdout.fnmatch_lines(["*- Proofy report -*"])  # terminal summary banner

    data = _load_results(pytester.path)
    assert data.get("count") == 3
    items = {item["path"]: item for item in data["items"]}

    # Locate by nodeid path
    pass_item = next(v for k, v in items.items() if k.endswith("::test_pass"))
    fail_item = next(v for k, v in items.items() if k.endswith("::test_fail"))
    skip_item = next(v for k, v in items.items() if k.endswith("::test_skip"))

    # Passed test metadata
    assert pass_item["name"] == "My Special Name"
    assert pass_item["status"] == 1  # ResultStatus.PASSED
    assert pass_item["attributes"].get("team") == "A"
    assert "slow" in pass_item.get("markers", [])

    # Failed assertion remains FAILED
    assert fail_item["status"] == 2  # ResultStatus.FAILED
    assert fail_item.get("message") is None or "AssertionError" in str(fail_item.get("message"))

    # Skipped test captures skip status and reason
    assert skip_item["status"] == 4  # ResultStatus.SKIPPED
    assert "because" in (skip_item.get("message") or "").lower()


def test_env_propagation_and_custom_output_dir(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        test_env="""
        def test_env():
            # The plugin should honor the CLI output dir when backing up results.
            # We avoid asserting environment variables because the parent test session
            # may have already set them and the plugin uses setdefault.
            assert True
        """
    )

    result = pytester.runpytest(
        "--proofy",
        "--proofy-mode=batch",
        "--proofy-output-dir=custom_out",
        "--proofy-backup",
    )
    result.assert_outcomes(passed=1)

    # Backup should respect custom output directory
    data = _load_results(pytester.path, rel_dir="custom_out")
    assert isinstance(data.get("items"), list)


def test_broken_status_for_non_assertion_error(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        test_broken="""
        def test_broken():
            raise RuntimeError("boom")
        """
    )

    result = pytester.runpytest("--proofy", "--proofy-backup")
    result.assert_outcomes(failed=1)

    data = _load_results(pytester.path)
    items = {item["path"]: item for item in data["items"]}
    broken_item = next(v for k, v in items.items() if k.endswith("::test_broken"))
    assert broken_item["status"] == 3  # ResultStatus.BROKEN
    assert "runtimeerror" in (broken_item.get("message") or "").lower()


def test_skipped_tests_via_mark_and_skipif(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        test_skips="""
        import pytest

        @pytest.mark.skip(reason="decorator reason")
        def test_skip_marker():
            assert False

        @pytest.mark.skipif(True, reason="cond reason")
        def test_skip_if():
            assert False
        """
    )

    result = pytester.runpytest("--proofy", "--proofy-backup")
    # Both tests should be skipped
    result.assert_outcomes(skipped=2)

    data = _load_results(pytester.path)
    items = {item["path"]: item for item in data["items"]}

    marker_item = next(v for k, v in items.items() if k.endswith("::test_skip_marker"))
    skipif_item = next(v for k, v in items.items() if k.endswith("::test_skip_if"))

    assert marker_item["status"] == 4  # SKIPPED
    assert skipif_item["status"] == 4  # SKIPPED

    # Message should contain reasons coming from mark and skipif
    assert "decorator reason" in (marker_item.get("message") or "")
    assert "cond reason" in (skipif_item.get("message") or "")

    # The plugin excludes the 'skip' marker from markers list
    assert "skip" not in (marker_item.get("markers") or [])


def test_plugin_activation_via_cli_flag(pytester: pytest.Pytester) -> None:
    """Test that plugin activates when --proofy flag is provided."""
    pytester.makepyfile(
        test_activation="""
        def test_simple():
            assert True
        """
    )

    result = pytester.runpytest("--proofy", "--proofy-backup")
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*- Proofy report -*"])  # Plugin should be active

    # Results file should be created
    data = _load_results(pytester.path)
    assert data.get("count") == 1


def test_plugin_activation_via_pytest_ini(pytester: pytest.Pytester) -> None:
    """Test that plugin activates when proofy=true is set in pytest.ini."""
    pytester.makeini(
        """
        [pytest]
        proofy = True
        proofy_backup = True
        """
    )

    pytester.makepyfile(
        test_activation="""
        def test_simple():
            assert True
        """
    )

    # Run WITHOUT --proofy flag - should activate via ini
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)
    result.stdout.fnmatch_lines(["*- Proofy report -*"])

    # Results file should be created
    data = _load_results(pytester.path)
    assert data.get("count") == 1


def test_plugin_deactivation_without_flag_or_ini(pytester: pytest.Pytester) -> None:
    """Test that plugin does NOT activate when neither --proofy nor ini config is set."""
    pytester.makepyfile(
        test_deactivation="""
        def test_simple():
            assert True
        """
    )

    result = pytester.runpytest()
    result.assert_outcomes(passed=1)

    # Plugin should NOT be active - no Proofy report
    stdout = "\n".join(result.outlines)
    assert "Proofy report" not in stdout

    # Results file should NOT be created
    results_path = pytester.path / "proofy-artifacts" / "results.json"
    assert not results_path.exists(), "Results file should not exist when plugin is disabled"


def test_proofy_decorators_work_when_plugin_disabled(pytester: pytest.Pytester) -> None:
    """Test that proofy decorators and API calls don't cause errors when plugin is disabled."""
    pytester.makepyfile(
        test_decorators="""
        import pytest
        from proofy import name, description, severity, attributes
        from proofy import set_name, add_attributes, add_data

        @name("Test Name")
        @description("Test Description")
        @severity("critical")
        @attributes(component="auth")
        def test_with_decorators():
            # These should work or be no-ops when plugin disabled
            set_name("Runtime Name")
            add_attributes(env="test")
            add_data("test data", name="test_data")
            assert True
        
        @pytest.mark.proofy_attributes(team="A")
        def test_with_pytest_marks():
            assert True
        """
    )

    # Run WITHOUT --proofy flag - plugin disabled
    result = pytester.runpytest()
    result.assert_outcomes(passed=2)

    # No errors should occur
    assert result.ret == 0


def test_multiple_run_attributes_via_cli(pytester: pytest.Pytester) -> None:
    """Test that multiple --proofy-run-attributes flags are properly merged."""
    pytester.makepyfile(
        test_attrs="""
        def test_simple():
            assert True
        """
    )

    result = pytester.runpytest(
        "--proofy",
        "--proofy-backup",
        "--proofy-run-attributes",
        "alfa=1",
        "--proofy-run-attributes",
        "beta=22",
        "--proofy-run-attributes",
        "delta=44",
    )
    result.assert_outcomes(passed=1)

    data = _load_results(pytester.path)
    attributes = data.get("run_attributes", {})

    # All flags should merge into a single dictionary
    assert attributes.get("alfa") == "1"
    assert attributes.get("beta") == "22"
    assert attributes.get("delta") == "44"


def test_run_attributes_via_ini(pytester: pytest.Pytester) -> None:
    """Test that comma-separated run attributes are properly parsed."""
    pytester.makeini(
        """
        [pytest]
        proofy = True
        proofy_backup = True
        proofy_run_attributes =
            alfa=1
            beta=22
            delta=44
        """
    )
    pytester.makepyfile(
        test_attrs="""
        def test_simple():
            assert True
        """
    )

    result = pytester.runpytest()
    result.assert_outcomes(passed=1)

    data = _load_results(pytester.path)
    attributes = data.get("run_attributes", {})

    # All comma-separated attributes should be parsed
    assert attributes.get("alfa") == "1"
    assert attributes.get("beta") == "22"
    assert attributes.get("delta") == "44"


def test_run_attributest_via_environment_variable(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that run attributes are properly parsed from environment variable."""
    pytester.makepyfile(
        test_attrs="""
        def test_simple():
            assert True
        """
    )
    monkeypatch.setenv("PROOFY_RUN_ATTRIBUTES", "alfa=1,beta=22,delta=44")
    monkeypatch.setenv("PROOFY_TOKEN", "test-token")
    monkeypatch.setenv("PROOFY_PROJECT_ID", "12345")
    monkeypatch.setenv("PROOFY_API_BASE", "https://example.invalid")
    monkeypatch.setenv("PROOFY", "true")
    monkeypatch.setenv("PROOFY_BACKUP", "true")
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)

    data = _load_results(pytester.path)
    attributes = data.get("run_attributes", {})
    assert attributes.get("alfa") == "1"
    assert attributes.get("beta") == "22"
    assert attributes.get("delta") == "44"
