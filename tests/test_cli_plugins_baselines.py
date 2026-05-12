# tests/test_cli_plugins_baselines.py
# Tests for the nexus plugins baselines subcommands.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus plugins baselines list and delete subcommands."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.instances.registry import InstanceRegistry
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


def _info(plugin_id: str) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": "1.0.0",
            "state": "active",
            "source": "servicenow",
            "product_family": "ITSM",
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
        }
    )


def _seed_instance(profile: str, plugins: tuple[PluginInfo, ...] | None = None) -> None:
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    registry.register(_meta(profile))
    if plugins is not None:
        inv = PluginInventory(
            captured_at=datetime.now(UTC),
            sn_version="Xanadu",
            plugins=plugins,
        )
        registry.save_plugin_inventory(profile, inv)


def _seed_baseline(profile: str, name: str = "default") -> None:
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    inv = PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=(_info("com.snc.x"),),
    )
    registry.save_plugin_baseline(profile, name, inv)


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_baselines_list_shows_no_baselines_message(
    runner: CliRunner, tmp_path: Path
) -> None:
    """When no baselines exist, list prints an info notice."""
    _seed_instance("prod", (_info("com.snc.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "baselines", "list"])
    assert result.exit_code == 0
    assert "no baselines" in result.output.lower()


def test_baselines_list_renders_table_with_baselines(
    runner: CliRunner, tmp_path: Path
) -> None:
    """When baselines exist, list renders a DataTable with their names."""
    _seed_instance("prod", (_info("com.snc.x"),))
    _seed_baseline("prod", "default")
    _seed_baseline("prod", "pre-upgrade")
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "baselines", "list"])
    assert result.exit_code == 0
    assert "default" in result.output
    assert "pre-upgrade" in result.output


def test_baselines_delete_with_yes_flag_removes_baseline(
    runner: CliRunner, tmp_path: Path
) -> None:
    """--yes skips confirmation and deletes the baseline."""
    _seed_instance("prod", (_info("com.snc.x"),))
    _seed_baseline("prod", "default")
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "baselines", "delete", "default", "--yes"])
    assert result.exit_code == 0
    assert "deleted" in result.output.lower()
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    assert registry.load_plugin_baseline("prod", "default") is None


def test_baselines_delete_missing_baseline_exits_one(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Deleting a baseline that does not exist exits 1."""
    _seed_instance("prod", (_info("com.snc.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "baselines", "delete", "nope", "--yes"])
    assert result.exit_code == 1
    assert "nope" in result.output


def test_baselines_delete_invalid_name_exits_one(
    runner: CliRunner, tmp_path: Path
) -> None:
    """An invalid baseline name exits 1 with the validation message."""
    _seed_instance("prod", (_info("com.snc.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "baselines", "delete", "BAD NAME", "--yes"])
    assert result.exit_code == 1
    assert "invalid baseline name" in result.output.lower()
