# tests/test_cli_plugins_updates.py
# Tests for the nexus plugins updates command.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for nexus plugins updates."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml as _yaml
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
    latest_version: str | None = None,
    product_family: str = "Uncategorized",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": version,
            "state": "active",
            "source": "store",
            "product_family": product_family,
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
            "latest_version": latest_version,
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


def test_plugins_updates_renders_datatable_with_pending_updates(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),
            _info("com.acme.other", version="2.0.0", latest_version="2.0.0"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates"])
    assert result.exit_code == 0
    assert "com.acme.helper" in result.output
    assert "3.0.0" in result.output
    assert "3.1.0" in result.output
    assert "com.acme.other" not in result.output


def test_plugins_updates_prints_up_to_date_when_all_current(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.1.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates"])
    assert result.exit_code == 0
    assert "Up to date" in result.output


def test_plugins_updates_writes_yaml_when_queue_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    out_file = tmp_path / "queue.yaml"
    result = runner.invoke(app, ["plugins", "updates", "--queue", str(out_file)])
    assert result.exit_code == 0
    payload = _yaml.safe_load(out_file.read_text(encoding="utf-8"))
    assert payload["instance"] == "prod"
    assert payload["captured_at"]
    assert len(payload["updates"]) == 1
    update = payload["updates"][0]
    assert update["plugin_id"] == "com.acme.helper"
    assert update["current_version"] == "3.0.0"
    assert update["latest_version"] == "3.1.0"


def test_plugins_updates_does_not_write_yaml_when_queue_flag_omitted(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    cwd_before = list(tmp_path.iterdir())
    runner.invoke(app, ["plugins", "updates"])
    cwd_after = list(tmp_path.iterdir())
    assert cwd_before == cwd_after


def test_plugins_updates_warns_when_inventory_missing(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", None)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates"])
    assert result.exit_code != 0
    assert "nexus instance refresh" in result.output


def test_plugins_updates_prints_pre_update_refresh_hint_when_queue_written(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    out_file = tmp_path / "queue.yaml"
    result = runner.invoke(app, ["plugins", "updates", "--queue", str(out_file)])
    assert "Before applying" in result.output
    assert "nexus instance refresh" in result.output


def test_updates_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert "updates" in payload
    assert payload["updates"][0]["plugin_id"] == "com.acme.helper"


def test_updates_errors_on_unknown_format_value(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output
