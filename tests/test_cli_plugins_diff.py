# tests/test_cli_plugins_diff.py
# Tests for nexus plugins diff and nexus plugins promote.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for the cross-instance plugin commands."""

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


def _info(
    plugin_id: str,
    *,
    version: str = "1.0.0",
    state: str = "active",
    product_family: str = "ITSM",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": version,
            "state": state,
            "source": "servicenow",
            "product_family": product_family,
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
        }
    )


def _seed(
    tmp_path: Path,
    profile: str,
    plugins: tuple[PluginInfo, ...] | None,
) -> None:
    profile_dir = tmp_path / "instances" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(
        _meta(profile).model_dump_json(indent=2), encoding="utf-8"
    )
    if plugins is not None:
        inv = PluginInventory(
            captured_at=datetime.now(UTC),
            sn_version="Xanadu",
            plugins=plugins,
        )
        (profile_dir / "plugins.json").write_text(inv.model_dump_json(indent=2), encoding="utf-8")


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_plugins_diff_renders_datatable_with_all_status_categories(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.snc.problem"),
            _info("com.snc.incident", version="2.0.0"),
            _info("com.snc.discovery", state="active"),
        ),
    )
    _seed(
        tmp_path,
        "dev",
        (
            _info("com.snc.incident", version="1.0.0"),
            _info("com.snc.discovery", state="inactive"),
            _info("com.snc.legacy"),
        ),
    )
    result = runner.invoke(app, ["plugins", "diff", "prod", "dev"])
    assert result.exit_code == 0
    out = result.output
    assert "com.snc.problem" in out
    assert "com.snc.incident" in out
    assert "com.snc.discovery" in out
    assert "com.snc.legacy" in out


def test_plugins_diff_filters_by_status_flag(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.problem"), _info("com.snc.incident")))
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    result = runner.invoke(app, ["plugins", "diff", "prod", "dev", "--status", "only_in_a"])
    assert result.exit_code == 0
    assert "com.snc.problem" in result.output
    assert "com.snc.incident" not in result.output


def test_plugins_diff_warns_when_either_inventory_missing(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.incident"),))
    _seed(tmp_path, "dev", None)  # meta only, no plugins.json
    result = runner.invoke(app, ["plugins", "diff", "prod", "dev"])
    assert result.exit_code != 0
    assert "nexus instance refresh" in result.output


def test_plugins_diff_errors_when_profile_unknown(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.incident"),))
    result = runner.invoke(app, ["plugins", "diff", "prod", "nonexistent"])
    assert result.exit_code != 0


def test_plugins_diff_with_identical_inventories_prints_no_differences(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.incident"),))
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    result = runner.invoke(app, ["plugins", "diff", "prod", "dev"])
    assert result.exit_code == 0
    assert "No differences" in result.output
