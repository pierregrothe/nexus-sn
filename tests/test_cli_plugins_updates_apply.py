# tests/test_cli_plugins_updates_apply.py
# Tests for `nexus plugins updates` --family / --apply / --out flags.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the batch-upgrade extensions on `nexus plugins updates`."""

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
    pid: str,
    *,
    version: str = "1.0.0",
    latest_version: str | None = "2.0.0",
    family: str = "Uncategorized",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": pid,
            "name": pid,
            "version": version,
            "state": "active",
            "source": "store",
            "product_family": family,
            "depends_on": (),
            "sys_id": f"sys-{pid}",
            "installed_at": None,
            "latest_version": latest_version,
        }
    )


def _seed(tmp_path: Path, profile: str, plugins: tuple[PluginInfo, ...]) -> None:
    profile_dir = tmp_path / "instances" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(
        _meta(profile).model_dump_json(indent=2), encoding="utf-8"
    )
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


def test_plugins_updates_family_filter_shrinks_pending(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.acme.incident", family="ITSM"),
            _info("com.acme.cmdb", family="ITOM"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates", "--family", "ITSM"])
    assert result.exit_code == 0
    assert "com.acme.incident" in result.output
    assert "com.acme.cmdb" not in result.output
