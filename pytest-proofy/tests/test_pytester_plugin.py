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

        @pytest.mark.proofy_attributes(team="A", __proofy_tags=["t1", "t2"], __proofy_name="My Special Name")
        @pytest.mark.slow
        def test_pass():
            assert True

        def test_fail():
            assert 0

        def test_skip():
            pytest.skip("because we want to")
        """
    )

    result = pytester.runpytest("--proofy-always-backup")
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
    assert set(pass_item["tags"]) == {"t1", "t2"}
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
        "--proofy-mode=batch",
        "--proofy-output-dir=custom_out",
        "--proofy-always-backup",
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

    result = pytester.runpytest("--proofy-always-backup")
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

    result = pytester.runpytest("--proofy-always-backup")
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
