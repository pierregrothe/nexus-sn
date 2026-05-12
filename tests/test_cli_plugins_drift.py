# tests/test_cli_plugins_drift.py
# Tests for the nexus plugins drift command.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus plugins drift (audit baseline + current snapshots)."""

import json
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


def _seed_current(
    profile: str,
    plugins: tuple[PluginInfo, ...] | None = None,
) -> None:
    """Write meta + plugins.json (current snapshot) for a profile."""
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


def _seed_baseline(
    profile: str,
    plugins: tuple[PluginInfo, ...],
) -> None:
    """Write plugins.baseline.json for a profile (profile dir must already exist)."""
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    inv = PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )
    registry.save_plugin_baseline(profile, inv)


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_drift_errors_when_no_current_snapshot(runner: CliRunner, tmp_path: Path) -> None:
    """No plugins.json captured yet -> exit 1 with refresh hint."""
    _seed_current("prod", plugins=None)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift"])
    assert result.exit_code == 1
    assert "refresh" in result.output.lower()


def test_drift_errors_when_no_baseline_with_hint(runner: CliRunner, tmp_path: Path) -> None:
    """Current exists, no baseline -> exit 1 with --ack hint."""
    _seed_current("prod", (_info("com.snc.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift"])
    assert result.exit_code == 1
    assert "--ack" in result.output


def test_drift_ack_sets_baseline(runner: CliRunner, tmp_path: Path) -> None:
    """--ack saves current snapshot as plugins.baseline.json."""
    _seed_current("prod", (_info("com.snc.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--ack"])
    assert result.exit_code == 0
    assert "Baseline set" in result.output
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    baseline = registry.load_plugin_baseline("prod")
    assert baseline is not None
    assert len(baseline.plugins) == 1
    assert baseline.plugins[0].plugin_id == "com.snc.x"


def test_drift_ack_errors_when_no_current_snapshot(runner: CliRunner, tmp_path: Path) -> None:
    """--ack with no plugins.json -> exit 1 with refresh hint."""
    _seed_current("prod", plugins=None)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--ack"])
    assert result.exit_code == 1
    assert "refresh" in result.output.lower()


def test_drift_reports_no_drift_when_inventories_identical(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Same plugin in baseline and current -> 'No drift detected.'"""
    plugins = (_info("com.snc.x"),)
    _seed_current("prod", plugins)
    _seed_baseline("prod", plugins)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift"])
    assert result.exit_code == 0
    assert "No drift detected" in result.output


def test_drift_renders_added_removed_version_state_changes(
    runner: CliRunner, tmp_path: Path
) -> None:
    """Mixed drift renders DataTable with each status."""
    baseline = (
        _info("com.gone"),
        _info("com.flip", state="inactive"),
        _info("com.bump", version="1.0.0"),
    )
    current = (
        _info("com.new"),
        _info("com.flip", state="active"),
        _info("com.bump", version="2.0.0"),
    )
    # _seed_current MUST come before _seed_baseline because it calls registry.register()
    # which creates the profile directory that save_plugin_baseline requires.
    _seed_current("prod", current)
    _seed_baseline("prod", baseline)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift"])
    assert result.exit_code == 0
    assert "com.new" in result.output
    assert "com.gone" in result.output
    assert "com.flip" in result.output
    assert "com.bump" in result.output


def test_drift_emits_json_when_format_flag_provided(runner: CliRunner, tmp_path: Path) -> None:
    """--format json emits a PluginDriftReport JSON to stdout."""
    baseline = (_info("com.snc.x", version="1.0.0"),)
    current = (_info("com.snc.x", version="2.0.0"),)
    _seed_current("prod", current)
    _seed_baseline("prod", baseline)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert payload["profile"] == "prod"
    assert "entries" in payload
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["status"] == "version_changed"


def test_drift_emits_empty_entries_json_when_no_drift(runner: CliRunner, tmp_path: Path) -> None:
    """--format json emits {"entries": []} when no drift -- CI-parseable."""
    plugins = (_info("com.snc.x"),)
    _seed_current("prod", plugins)
    _seed_baseline("prod", plugins)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert payload["entries"] == []


def test_drift_errors_on_unknown_format_value(runner: CliRunner, tmp_path: Path) -> None:
    """--format yaml exits 1 with the standard Unknown --format message."""
    _seed_current("prod", (_info("com.snc.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output


def test_drift_strict_exits_1_when_drift_detected(runner: CliRunner, tmp_path: Path) -> None:
    """--strict + drift present -> exit 1 after rendering."""
    baseline = (_info("com.snc.x", version="1.0.0"),)
    current = (_info("com.snc.x", version="2.0.0"),)
    _seed_current("prod", current)
    _seed_baseline("prod", baseline)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--strict"])
    assert result.exit_code == 1


def test_drift_strict_exits_0_when_no_drift(runner: CliRunner, tmp_path: Path) -> None:
    """--strict + no drift -> exit 0."""
    plugins = (_info("com.snc.x"),)
    _seed_current("prod", plugins)
    _seed_baseline("prod", plugins)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--strict"])
    assert result.exit_code == 0
    assert "No drift detected" in result.output


def test_drift_strict_json_emits_report_and_exits_1(runner: CliRunner, tmp_path: Path) -> None:
    """--strict --format json with drift -> emits JSON to stdout, exits 1."""
    baseline = (_info("com.snc.x", version="1.0.0"),)
    current = (_info("com.snc.x", version="2.0.0"),)
    _seed_current("prod", current)
    _seed_baseline("prod", baseline)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "drift", "--strict", "--format", "json"])
    assert result.exit_code == 1
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert len(payload["entries"]) == 1
