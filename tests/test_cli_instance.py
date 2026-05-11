# tests/test_cli_instance.py
# Tests for nexus instance CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for the nexus instance sub-app."""

from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import _pick_existing_oauth_app, app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta


def _meta(profile: str = "dev12345") -> InstanceMeta:
    return InstanceMeta.create(
        profile=profile,
        url=f"https://{profile}.service-now.com",
        username="admin",
        client_id="client-123",
        sn_version="Xanadu",
        sn_build="04-01-2025",
        instance_name=profile,
        token_expires_in=1800,
    )


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def _write_meta(tmp_path: Path, meta: InstanceMeta) -> None:
    profile_dir = tmp_path / "instances" / meta.profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")


def test_instance_callback_with_no_subcommand_shows_instances(
    runner: CliRunner, tmp_path: Path
) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance"])
    assert result.exit_code == 0
    assert "dev12345" in result.output
    assert "nexus instance" in result.output


def test_instance_callback_with_no_subcommand_shows_commands(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["instance"])
    assert result.exit_code == 0
    assert "register" in result.output
    assert "connect" in result.output
    assert "nexus instance" in result.output


def test_instance_list_with_no_instances_prints_empty_message(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["instance", "list"])
    assert result.exit_code == 0
    assert "No instances registered" in result.output


def test_instance_list_shows_registered_profiles(runner: CliRunner, tmp_path: Path) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "list"])
    assert result.exit_code == 0
    assert "dev12345" in result.output


def test_instance_status_shows_meta_fields(runner: CliRunner, tmp_path: Path) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "status", "dev12345"])
    assert result.exit_code == 0
    assert "dev12345" in result.output
    assert "Xanadu" in result.output


def test_instance_status_without_snapshot_shows_no_snapshot_message(
    runner: CliRunner, tmp_path: Path
) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "status", "dev12345"])
    assert result.exit_code == 0
    assert "No snapshot" in result.output


def test_instance_status_with_unknown_profile_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["instance", "status", "nonexistent"])
    assert result.exit_code != 0


def test_instance_delete_removes_profile_directory(runner: CliRunner, tmp_path: Path) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "delete", "dev12345", "--force"])
    assert result.exit_code == 0
    assert not (tmp_path / "instances" / "dev12345").exists()


def test_instance_delete_unknown_profile_exits_nonzero(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["instance", "delete", "nonexistent", "--force"])
    assert result.exit_code != 0


def test_instance_use_sets_default_in_config(runner: CliRunner, tmp_path: Path) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "use", "dev12345"])
    assert result.exit_code == 0
    config_raw = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "dev12345" in config_raw


def test_instance_use_unknown_profile_exits_nonzero(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["instance", "use", "nonexistent"])
    assert result.exit_code != 0


def test_instance_connect_with_unknown_profile_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["instance", "connect", "nonexistent"])
    assert result.exit_code != 0


def test_instance_refresh_with_unknown_profile_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["instance", "refresh", "nonexistent"])
    assert result.exit_code != 0


def test_instance_register_with_existing_profile_exits_nonzero(
    runner: CliRunner, tmp_path: Path
) -> None:
    _write_meta(tmp_path, _meta("dev12345"))
    result = runner.invoke(app, ["instance", "register", "dev12345"])
    assert result.exit_code != 0
    assert "already exists" in result.output


_OAUTH_ENTRY: dict[str, str] = {
    "name": "nexus-prod",
    "client_id": "existing-client-id",
    "sys_id": "sys123",
    "sys_created_on": "2026-05-01",
}


def _scripted_prompt(answers: list[str]) -> object:
    """Return a typer.prompt replacement that yields ``answers`` in order."""
    queue = iter(answers)

    def _prompt(*_args: object, **_kwargs: object) -> str:
        return next(queue)

    return _prompt


def test_pick_existing_oauth_app_returns_picked_entry_with_prompted_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(typer, "prompt", _scripted_prompt(["1", "user-pasted-secret"]))
    result = _pick_existing_oauth_app([_OAUTH_ENTRY], profile="dev")
    assert result == ("existing-client-id", "user-pasted-secret")


def test_pick_existing_oauth_app_returns_none_when_user_picks_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(typer, "prompt", _scripted_prompt(["n"]))
    result = _pick_existing_oauth_app([_OAUTH_ENTRY], profile="dev")
    assert result is None


def test_pick_existing_oauth_app_returns_none_on_invalid_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(typer, "prompt", _scripted_prompt(["abc"]))
    result = _pick_existing_oauth_app([_OAUTH_ENTRY], profile="dev")
    assert result is None


def test_pick_existing_oauth_app_returns_none_on_out_of_range_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(typer, "prompt", _scripted_prompt(["5"]))
    result = _pick_existing_oauth_app([_OAUTH_ENTRY], profile="dev")
    assert result is None


def test_pick_existing_oauth_app_uses_picked_index_among_multiple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    second = {
        "name": "nexus-dev",
        "client_id": "second-client",
        "sys_id": "sys456",
        "sys_created_on": "2026-05-02",
    }
    monkeypatch.setattr(typer, "prompt", _scripted_prompt(["2", "second-secret"]))
    result = _pick_existing_oauth_app([_OAUTH_ENTRY, second], profile="dev")
    assert result == ("second-client", "second-secret")
