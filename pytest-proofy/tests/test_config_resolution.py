from __future__ import annotations

from typing import Any

import pytest
from pytest_proofy.config import resolve_options


class DummyConfig:
    """Minimal stand-in for pytest.Config used by resolve_options.

    Provides getoption/getini lookups from supplied dictionaries.
    """

    def __init__(
        self, *, cli: dict[str, Any] | None = None, ini: dict[str, Any] | None = None
    ) -> None:
        self._cli = cli or {}
        self._ini = ini or {}

    def getoption(self, name: str, default: Any | None = None) -> Any | None:
        return self._cli.get(name, default)

    def getini(self, name: str) -> Any | None:
        return self._ini.get(name)


def test_defaults_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROOFY", raising=False)
    cfg = DummyConfig()
    resolved = resolve_options(cfg)
    assert resolved.enabled is False


@pytest.mark.parametrize(
    "cli_val, env_val, ini_val, expected",
    [
        (True, "false", "false", True),  # CLI wins
        (None, "1", "false", True),  # ENV wins over INI
        (None, None, "True", True),  # INI enables
        (None, None, "no", False),  # INI disables
    ],
)
def test_activation_precedence(
    cli_val: Any,
    env_val: Any,
    ini_val: Any,
    expected: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if env_val is None:
        monkeypatch.delenv("PROOFY", raising=False)
    else:
        monkeypatch.setenv("PROOFY", str(env_val))
    cfg = DummyConfig(
        cli={"proofy": cli_val} if cli_val is not None else {},
        ini={"proofy": ini_val} if ini_val is not None else {},
    )
    resolved = resolve_options(cfg)
    assert resolved.enabled is expected


@pytest.mark.parametrize(
    "field, cli_key, env_key, ini_key, cli_val, env_val, ini_val",
    [
        (
            "api_base",
            "proofy_api_base",
            "PROOFY_API_BASE",
            "proofy_api_base",
            "https://cli.example",
            "https://env.example",
            "https://ini.example",
        ),
        (
            "token",
            "proofy_token",
            "PROOFY_TOKEN",
            "proofy_token",
            "cli_token",
            "env_token",
            "ini_token",
        ),
        (
            "output_dir",
            "proofy_output_dir",
            "PROOFY_OUTPUT_DIR",
            "proofy_output_dir",
            "cli_out",
            "env_out",
            "ini_out",
        ),
        (
            "run_name",
            "proofy_run_name",
            "PROOFY_RUN_NAME",
            "proofy_run_name",
            "cli-run",
            "env-run",
            "ini-run",
        ),
    ],
)
def test_string_option_precedence(
    field: str,
    cli_key: str,
    env_key: str,
    ini_key: str,
    cli_val: str,
    env_val: str,
    ini_val: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROOFY", "true")

    # CLI wins
    monkeypatch.setenv(env_key, env_val)
    cfg = DummyConfig(cli={"proofy": True, cli_key: cli_val}, ini={ini_key: ini_val})
    resolved = resolve_options(cfg)
    assert getattr(resolved, field) == cli_val

    # ENV wins when CLI missing
    cfg = DummyConfig(cli={"proofy": True}, ini={ini_key: ini_val})
    resolved = resolve_options(cfg)
    assert getattr(resolved, field) == env_val

    # INI used when CLI and ENV missing
    monkeypatch.delenv(env_key, raising=False)
    cfg = DummyConfig(cli={"proofy": True}, ini={ini_key: ini_val})
    resolved = resolve_options(cfg)
    assert getattr(resolved, field) == ini_val


@pytest.mark.parametrize(
    "field, cli_key, env_key, ini_key, cli_val, env_val, ini_val, default",
    [
        (
            "project_id",
            "proofy_project_id",
            "PROOFY_PROJECT_ID",
            "proofy_project_id",
            11,
            "22",
            "33",
            None,
        ),
        (
            "batch_size",
            "proofy_batch_size",
            "PROOFY_BATCH_SIZE",
            "proofy_batch_size",
            77,
            "88",
            "99",
            10,
        ),
        (
            "run_id",
            "proofy_run_id",
            "PROOFY_RUN_ID",
            "proofy_run_id",
            123,
            "456",
            "789",
            None,
        ),
    ],
)
def test_int_option_precedence_and_parsing(
    field: str,
    cli_key: str,
    env_key: str,
    ini_key: str,
    cli_val: int,
    env_val: str,
    ini_val: str,
    default: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROOFY", "true")

    # CLI wins
    monkeypatch.setenv(env_key, env_val)
    cfg = DummyConfig(cli={"proofy": True, cli_key: cli_val}, ini={ini_key: ini_val})
    resolved = resolve_options(cfg)
    assert getattr(resolved, field) == cli_val

    # ENV wins when CLI missing
    cfg = DummyConfig(cli={"proofy": True}, ini={ini_key: ini_val})
    resolved = resolve_options(cfg)
    assert getattr(resolved, field) == int(env_val)

    # INI used when CLI and ENV missing
    monkeypatch.delenv(env_key, raising=False)
    cfg = DummyConfig(cli={"proofy": True}, ini={ini_key: ini_val})
    resolved = resolve_options(cfg)
    assert getattr(resolved, field) == int(ini_val)

    # Invalid ENV falls back to default
    if default is not None:
        monkeypatch.setenv(env_key, "not_an_int")
        cfg = DummyConfig(cli={"proofy": True}, ini={})
        resolved = resolve_options(cfg)
        assert getattr(resolved, field) == default
    else:
        monkeypatch.setenv(env_key, "not_an_int")
        cfg = DummyConfig(cli={"proofy": True}, ini={})
        resolved = resolve_options(cfg)
        assert getattr(resolved, field) is None


@pytest.mark.parametrize(
    "env_val, expected",
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("maybe", False),
    ],
)
def test_bool_parsing_for_backup(
    env_val: str, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROOFY", "true")
    monkeypatch.setenv("PROOFY_BACKUP", env_val)
    cfg = DummyConfig(cli={"proofy": True}, ini={})
    resolved = resolve_options(cfg)
    assert resolved.always_backup is expected


def test_mode_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROOFY", "true")
    monkeypatch.setenv("PROOFY_MODE", "lazy")
    cfg = DummyConfig(cli={"proofy": True, "proofy_mode": "batch"}, ini={"proofy_mode": "live"})
    resolved = resolve_options(cfg)
    # CLI should win
    assert resolved.mode == "batch"

    # ENV wins if CLI missing
    cfg = DummyConfig(cli={"proofy": True}, ini={"proofy_mode": "live"})
    resolved = resolve_options(cfg)
    assert resolved.mode == "lazy"

    # INI wins if CLI/ENV missing
    monkeypatch.delenv("PROOFY_MODE", raising=False)
    cfg = DummyConfig(cli={"proofy": True}, ini={"proofy_mode": "live"})
    resolved = resolve_options(cfg)
    assert resolved.mode == "live"


def test_run_attributes_parsing_cli_and_ini_and_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PROOFY", "true")

    # CLI repeated flags
    cfg = DummyConfig(
        cli={"proofy": True, "proofy_run_attributes": ["alfa=1", "beta=22", "delta=44"]}
    )
    resolved = resolve_options(cfg)
    assert resolved.run_attributes == {"alfa": "1", "beta": "22", "delta": "44"}

    # INI linelist
    cfg = DummyConfig(cli={"proofy": True}, ini={"proofy_run_attributes": ["x=1", "y=2"]})
    resolved = resolve_options(cfg)
    assert resolved.run_attributes == {"x": "1", "y": "2"}

    # ENV comma-separated
    monkeypatch.setenv("PROOFY_RUN_ATTRIBUTES", "k=11, m = 22, n=33")
    cfg = DummyConfig(cli={"proofy": True}, ini={})
    resolved = resolve_options(cfg)
    assert resolved.run_attributes == {"k": "11", "m": "22", "n": "33"}


def test_run_attributes_invalid_env_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROOFY", "true")
    monkeypatch.setenv("PROOFY_RUN_ATTRIBUTES", "badpair, ok=1")
    cfg = DummyConfig(cli={"proofy": True}, ini={})
    with pytest.raises(ValueError):
        resolve_options(cfg)


def test_invalid_mode_rejected_by_parser_when_integration_running(
    pytester: pytest.Pytester,
) -> None:
    # This validates the CLI choices at parser level; plugin must be discoverable.
    pytester.makepyfile(
        test_sample="""
        def test_ok():
            assert True
        """
    )
    result = pytester.runpytest("--proofy", "--proofy-mode=invalid_mode")
    assert result.ret != 0
    stderr_text = "\n".join(result.errlines)
    assert "invalid choice" in stderr_text
    assert "--proofy-mode" in stderr_text


@pytest.mark.parametrize(
    "ini_val, expected",
    [
        ("True", True),
        ("False", False),
        ("yes", True),
        ("no", False),
        ("1", True),
        ("0", False),
    ],
)
def test_bool_parsing_for_backup_from_ini(
    ini_val: str, expected: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PROOFY", "true")
    cfg = DummyConfig(cli={"proofy": True}, ini={"proofy_backup": ini_val})
    resolved = resolve_options(cfg)
    assert resolved.always_backup is expected
