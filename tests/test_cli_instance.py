# tests/test_cli_instance.py
# Tests for nexus instance CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for the nexus instance sub-app."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.cli.oauth import (
    pick_existing_oauth_app as _pick_existing_oauth_app,
)
from nexus.cli.oauth import (
    print_generated_secret as _print_generated_secret,
)
from nexus.cli.oauth import (
    print_secret_recovery_steps as _print_secret_recovery_steps,
)
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta, InstanceSnapshot
from nexus.instances.registry import InstanceRegistry
from nexus.plugins.models import PluginInventory
from tests.conftest import scripted_prompt
from tests.fakes.scripted_prompt import ScriptedPromptSource


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


def test_instance_list_marks_default_profile_with_lime_asterisk(
    runner: CliRunner, tmp_path: Path
) -> None:
    """The default profile's row begins with the lime '* ' default marker."""
    _write_meta(tmp_path, _meta("alpha"))
    _write_meta(tmp_path, _meta("bravo"))
    use_result = runner.invoke(app, ["instance", "use", "alpha"])
    assert use_result.exit_code == 0

    list_result = runner.invoke(app, ["instance", "list"])
    assert list_result.exit_code == 0
    alpha_pos = list_result.output.index("alpha")
    bravo_pos = list_result.output.index("bravo")
    assert "* alpha" in list_result.output
    assert "* bravo" not in list_result.output
    assert alpha_pos < bravo_pos or alpha_pos > bravo_pos  # both present in output


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


def test_pick_existing_oauth_app_returns_picked_entry_with_prompted_secret() -> None:
    result = _pick_existing_oauth_app(
        [_OAUTH_ENTRY],
        profile="dev",
        url="https://dev.service-now.com",
        prompts=ScriptedPromptSource(["1", "user-pasted-secret"]),
    )
    assert result == ("existing-client-id", "user-pasted-secret")


def test_pick_existing_oauth_app_returns_none_when_user_picks_new() -> None:
    result = _pick_existing_oauth_app(
        [_OAUTH_ENTRY],
        profile="dev",
        url="https://dev.service-now.com",
        prompts=ScriptedPromptSource(["n"]),
    )
    assert result is None


def test_pick_existing_oauth_app_returns_none_on_invalid_choice() -> None:
    result = _pick_existing_oauth_app(
        [_OAUTH_ENTRY],
        profile="dev",
        url="https://dev.service-now.com",
        prompts=ScriptedPromptSource(["abc"]),
    )
    assert result is None


def test_pick_existing_oauth_app_returns_none_on_out_of_range_choice() -> None:
    result = _pick_existing_oauth_app(
        [_OAUTH_ENTRY],
        profile="dev",
        url="https://dev.service-now.com",
        prompts=ScriptedPromptSource(["5"]),
    )
    assert result is None


def test_pick_existing_oauth_app_uses_picked_index_among_multiple() -> None:
    second = {
        "name": "nexus-dev",
        "client_id": "second-client",
        "sys_id": "sys456",
        "sys_created_on": "2026-05-02",
    }
    result = _pick_existing_oauth_app(
        [_OAUTH_ENTRY, second],
        profile="dev",
        url="https://dev.service-now.com",
        prompts=ScriptedPromptSource(["2", "second-secret"]),
    )
    assert result == ("second-client", "second-secret")


def test_print_generated_secret_includes_value_and_save_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_generated_secret("super-secret-abc")
    out = capsys.readouterr().out
    assert "super-secret-abc" in out
    assert "Save this client secret" in out


def test_print_secret_recovery_steps_includes_sys_id_url_and_script(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _print_secret_recovery_steps(
        url="https://dev.service-now.com",
        sys_id="abc123",
        name="nexus-prod",
    )
    out = capsys.readouterr().out
    assert "https://dev.service-now.com/sys.scripts.do" in out
    assert "abc123" in out
    assert "getDecryptedValue" in out
    assert "nexus-prod" in out


def _empty_snapshot() -> InstanceSnapshot:
    return InstanceSnapshot(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
    )


def _setup_refresh_stubs(
    monkeypatch: pytest.MonkeyPatch,
    captured: dict[str, object],
) -> None:
    """Stub _acquire_token, PluginScanner, and InstanceScanner for refresh tests."""

    def fake_acquire(
        profile: str,
    ) -> tuple[InstanceRegistry, InstanceMeta, str, datetime]:
        paths = NexusPaths.from_env()
        registry = InstanceRegistry(paths.instances_dir)
        meta = registry.load(profile if profile else "prod")
        return registry, meta, "fake-token", datetime.now(UTC)

    class _FakePluginScanner:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def scan(
            self,
            url: str,
            token: str,
            sn_version: str,
            *,
            capture_counts: bool = True,
        ) -> PluginInventory:
            captured["capture_counts"] = capture_counts
            return PluginInventory(
                captured_at=datetime.now(UTC),
                sn_version=sn_version,
                plugins=(),
            )

    class _FakeInstanceScanner:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def scan(self, url: str, token: str, sn_version: str) -> InstanceSnapshot:
            return _empty_snapshot()

    monkeypatch.setattr("nexus.cli.commands_instance._acquire_token", fake_acquire)
    monkeypatch.setattr("nexus.cli.commands_instance.PluginScanner", _FakePluginScanner)
    monkeypatch.setattr("nexus.cli.commands_instance.InstanceScanner", _FakeInstanceScanner)


def test_instance_refresh_no_counts_flag_skips_count_capture(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`nexus instance refresh --no-counts` calls plugin scanner with capture_counts=False."""
    _write_meta(tmp_path, _meta("prod"))
    runner.invoke(app, ["instance", "use", "prod"])

    captured: dict[str, object] = {}
    _setup_refresh_stubs(monkeypatch, captured)

    result = runner.invoke(app, ["instance", "refresh", "prod", "--no-counts"])
    assert result.exit_code == 0, result.output
    assert captured.get("capture_counts") is False


def test_instance_refresh_without_no_counts_flag_captures_counts_by_default(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default behavior: capture_counts=True when --no-counts is not passed."""
    _write_meta(tmp_path, _meta("prod"))
    runner.invoke(app, ["instance", "use", "prod"])

    captured: dict[str, object] = {}
    _setup_refresh_stubs(monkeypatch, captured)

    result = runner.invoke(app, ["instance", "refresh", "prod"])
    assert result.exit_code == 0, result.output
    assert captured.get("capture_counts") is True


def test_instance_use_with_no_arg_and_single_profile_auto_picks(
    runner: CliRunner, tmp_path: Path
) -> None:
    """One registered instance + 'instance use' (no arg) -> auto-promote it."""
    _write_meta(tmp_path, _meta("only"))
    result = runner.invoke(app, ["instance", "use"])
    assert result.exit_code == 0, result.output
    assert "Only one instance registered" in result.output
    assert "Default instance set to 'only'" in result.output


def test_instance_use_with_no_arg_and_no_profiles_errors(runner: CliRunner, tmp_path: Path) -> None:
    """'instance use' (no arg, no instances) -> Exit 1 with Hint."""
    result = runner.invoke(app, ["instance", "use"])
    assert result.exit_code == 1
    assert "No instances registered" in result.output
    assert "nexus instance register" in result.output


def test_instance_use_with_no_arg_and_multiple_profiles_picks_via_prompt(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multiple instances + 'instance use' -> interactive picker reads stdin."""
    _write_meta(tmp_path, _meta("dev"))
    _write_meta(tmp_path, _meta("prod"))
    monkeypatch.setattr(typer, "prompt", scripted_prompt(["2"]))
    result = runner.invoke(app, ["instance", "use"])
    assert result.exit_code == 0, result.output
    assert "Multiple instances registered" in result.output
    # Second entry (alphabetically 'prod') becomes default
    assert "Default instance set to" in result.output


def test_instance_delete_promotes_survivor_when_only_one_remains(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Deleting the default with exactly one survivor -> auto-promote it."""
    _write_meta(tmp_path, _meta("dev"))
    _write_meta(tmp_path, _meta("prod"))
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["instance", "delete", "dev", "--force"])
    assert result.exit_code == 0, result.output
    assert "Default instance promoted to 'prod'" in result.output
