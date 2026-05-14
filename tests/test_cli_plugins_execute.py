# tests/test_cli_plugins_execute.py
# Tests for nexus plugins install/activate/upgrade/apply CLI commands.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the new plugin execution CLI commands."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _meta(profile: str) -> InstanceMeta:
    return InstanceMeta.create(
        profile=profile,
        url=f"https://{profile}.service-now.com",
        username="admin",
        client_id="cid",
        sn_version="Xanadu",
        sn_build="04-01-2025_1200",
        instance_name=profile,
        token_expires_in=1800,
    )


def _info(pid: str, state: str = "inactive") -> PluginInfo:
    return PluginInfo(
        plugin_id=pid,
        name=pid,
        version="1.0",
        state="active" if state == "active" else "inactive",
        source="servicenow",
        product_family="ITSM",
        depends_on=(),
        sys_id=f"sid-{pid}",
        installed_at=None,
    )


def _seed(tmp_path: Path, profile: str, plugins: tuple[PluginInfo, ...]) -> None:
    profile_dir = tmp_path / "instances" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(
        _meta(profile).model_dump_json(indent=2), encoding="utf-8"
    )
    inv = PluginInventory(captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=plugins)
    (profile_dir / "plugins.json").write_text(inv.model_dump_json(indent=2), encoding="utf-8")


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_plugins_install_command_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "install", "--help"])
    assert result.exit_code == 0
    assert "install" in result.output.lower()


def test_plugins_activate_command_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "activate", "--help"])
    assert result.exit_code == 0


def test_plugins_upgrade_command_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "upgrade", "--help"])
    assert result.exit_code == 0


def test_plugins_apply_command_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "apply", "--help"])
    assert result.exit_code == 0


def test_plugins_apply_with_missing_plan_file_errors(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "apply", str(tmp_path / "nope.yaml")])
    assert result.exit_code != 0


def test_plugins_bare_invocation_lists_new_commands(runner: CliRunner, tmp_path: Path) -> None:
    """The two-box discovery view should now show install/activate/upgrade/apply."""
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    for cmd in ("install", "activate", "upgrade", "apply"):
        assert cmd in result.output, f"missing {cmd} in plugins help output"


def test_plugins_deactivate_command_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "deactivate", "--help"])
    assert result.exit_code == 0
    assert "deactivate" in result.output.lower()
    assert "--force" in result.output


def test_plugins_uninstall_command_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "uninstall", "--help"])
    assert result.exit_code == 0
    assert "uninstall" in result.output.lower()
    assert "--force" in result.output


def test_plugins_bare_invocation_lists_deactivate_uninstall(
    runner: CliRunner, tmp_path: Path
) -> None:
    """`nexus plugins` bare-invocation discovery includes deactivate + uninstall."""
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    for cmd in ("deactivate", "uninstall"):
        assert cmd in result.output, f"missing {cmd} in plugins help output"
