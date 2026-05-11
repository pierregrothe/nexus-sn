# tests/test_cli_plugins.py
# Tests for the nexus plugins sub-app.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for nexus plugins list / info / export."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _meta(profile: str = "dev") -> InstanceMeta:
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
    product: str = "ITSM",
    source: Literal["servicenow", "store", "custom"] = "servicenow",
    state: Literal["active", "inactive"] = "active",
) -> PluginInfo:
    return PluginInfo(
        plugin_id=plugin_id,
        name=plugin_id,
        version="1.0",
        state=state,
        source=source,
        product_family=product,
        depends_on=(),
        sys_id=plugin_id,
        installed_at=None,
    )


def _seed(tmp_path: Path, profile: str, plugins: tuple[PluginInfo, ...]) -> None:
    profile_dir = tmp_path / "instances" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(
        _meta(profile).model_dump_json(indent=2), encoding="utf-8"
    )
    inv = PluginInventory(
        captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=plugins
    )
    (profile_dir / "plugins.json").write_text(
        inv.model_dump_json(indent=2), encoding="utf-8"
    )


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_plugins_list_shows_all_plugins_for_default_instance(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "dev",
        (_info("com.snc.incident"), _info("com.snc.discovery", product="ITOM")),
    )
    result = runner.invoke(app, ["instance", "use", "dev"])
    assert result.exit_code == 0
    result = runner.invoke(app, ["plugins", "list"])
    assert result.exit_code == 0
    assert "com.snc.incident" in result.output
    assert "com.snc.discovery" in result.output


def test_plugins_list_filters_by_product(runner: CliRunner, tmp_path: Path) -> None:
    _seed(
        tmp_path,
        "dev",
        (_info("com.snc.incident"), _info("com.snc.discovery", product="ITOM")),
    )
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "list", "--product", "ITSM"])
    assert "com.snc.incident" in result.output
    assert "com.snc.discovery" not in result.output


def test_plugins_list_filters_by_source(runner: CliRunner, tmp_path: Path) -> None:
    _seed(
        tmp_path,
        "dev",
        (
            _info("com.snc.incident"),
            _info("com.acme.helper", source="store", product="Uncategorized"),
        ),
    )
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "list", "--source", "store"])
    assert "com.acme.helper" in result.output
    assert "com.snc.incident" not in result.output


def test_plugins_list_filters_by_state(runner: CliRunner, tmp_path: Path) -> None:
    _seed(
        tmp_path,
        "dev",
        (_info("com.snc.incident"), _info("com.snc.legacy", state="inactive")),
    )
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "list", "--state", "inactive"])
    assert "com.snc.legacy" in result.output
    assert "com.snc.incident" not in result.output


def test_plugins_list_warns_when_no_inventory(
    runner: CliRunner, tmp_path: Path
) -> None:
    profile_dir = tmp_path / "instances" / "dev"
    profile_dir.mkdir(parents=True)
    (profile_dir / "meta.json").write_text(
        _meta("dev").model_dump_json(indent=2), encoding="utf-8"
    )
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "list"])
    assert "nexus instance refresh" in result.output
