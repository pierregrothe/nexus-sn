# tests/test_cli_plugins_orphans.py
# Tests for the nexus plugins orphans command.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus plugins orphans."""

import json
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
    depends_on: tuple[str, ...] = (),
    state: str = "active",
    record_count: int | None = 0,
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": "1.0",
            "state": state,
            "source": "store",
            "product_family": "Uncategorized",
            "depends_on": depends_on,
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
            "record_count": record_count,
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


def test_orphans_renders_datatable_with_orphan_candidates(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.lonely", record_count=0),
            _info("com.busy", record_count=100),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans"])
    assert result.exit_code == 0
    assert "com.lonely" in result.output
    assert "com.busy" not in result.output
    assert "1 orphan candidate" in result.output


def test_orphans_prints_no_candidates_message_when_clean(runner: CliRunner, tmp_path: Path) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.busy", record_count=100),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans"])
    assert result.exit_code == 0
    assert "No orphan candidates" in result.output


def test_orphans_filters_by_state_active_when_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.alive", state="active", record_count=0),
            _info("com.dead", state="inactive", record_count=0),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans", "--state", "active"])
    assert result.exit_code == 0
    assert "com.alive" in result.output
    assert "com.dead" not in result.output


def test_orphans_filters_by_state_inactive_when_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.alive", state="active", record_count=0),
            _info("com.dead", state="inactive", record_count=0),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans", "--state", "inactive"])
    assert result.exit_code == 0
    assert "com.dead" in result.output
    assert "com.alive" not in result.output


def test_orphans_errors_on_unknown_state_value(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x", record_count=0),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans", "--state", "weird"])
    assert result.exit_code == 1
    assert "Unknown --state" in result.output


def test_orphans_warns_when_snapshot_has_no_record_counts(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.unrefreshed", record_count=None),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans"])
    assert result.exit_code == 1
    assert "no record counts" in result.output.lower()
    assert "nexus instance refresh" in result.output


def test_orphans_warns_when_inventory_missing(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", None)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans"])
    assert result.exit_code == 1
    assert "nexus instance refresh" in result.output


def test_orphans_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.lonely", record_count=0),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert "candidates" in payload
    assert payload["candidates"][0]["plugin_id"] == "com.lonely"


def test_orphans_errors_on_unknown_format_value(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.x", record_count=0),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output
