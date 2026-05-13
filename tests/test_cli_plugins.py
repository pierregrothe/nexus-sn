# tests/test_cli_plugins.py
# Tests for the nexus plugins sub-app.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for nexus plugins list / info / export."""

import json
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
    inv = PluginInventory(captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=plugins)
    (profile_dir / "plugins.json").write_text(inv.model_dump_json(indent=2), encoding="utf-8")


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


def test_plugins_list_warns_when_no_inventory(runner: CliRunner, tmp_path: Path) -> None:
    profile_dir = tmp_path / "instances" / "dev"
    profile_dir.mkdir(parents=True)
    (profile_dir / "meta.json").write_text(_meta("dev").model_dump_json(indent=2), encoding="utf-8")
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "list"])
    assert "nexus instance refresh" in result.output


def test_plugins_info_renders_full_metadata(runner: CliRunner, tmp_path: Path) -> None:
    _seed(
        tmp_path,
        "dev",
        (
            PluginInfo(
                plugin_id="com.snc.discovery",
                name="Discovery",
                version="2.0",
                state="active",
                source="servicenow",
                product_family="ITOM",
                depends_on=("com.snc.cmdb",),
                sys_id="abc",
                installed_at=None,
            ),
        ),
    )
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "info", "com.snc.discovery"])
    assert result.exit_code == 0
    assert "com.snc.discovery" in result.output
    assert "Discovery" in result.output
    assert "ITOM" in result.output
    assert "com.snc.cmdb" in result.output


def test_plugins_info_with_unknown_plugin_exits_nonzero(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(app, ["plugins", "info", "com.snc.missing"])
    assert result.exit_code != 0
    assert "com.snc.missing" in result.output


def test_plugins_export_yaml_round_trips_through_plugin_inventory(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    runner.invoke(app, ["instance", "use", "dev"])
    out_file = tmp_path / "out.yaml"
    result = runner.invoke(
        app,
        ["plugins", "export", "--format", "yaml", "--out", str(out_file)],
    )
    assert result.exit_code == 0
    content = out_file.read_text(encoding="utf-8")
    assert "com.snc.incident" in content
    assert "Plugins:" in content or "plugins:" in content


def test_plugins_export_csv_emits_one_row_per_plugin(runner: CliRunner, tmp_path: Path) -> None:
    _seed(
        tmp_path,
        "dev",
        (_info("com.snc.incident"), _info("com.snc.problem")),
    )
    runner.invoke(app, ["instance", "use", "dev"])
    out_file = tmp_path / "out.csv"
    result = runner.invoke(
        app,
        ["plugins", "export", "--format", "csv", "--out", str(out_file)],
    )
    assert result.exit_code == 0
    lines = out_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3  # header + 2 rows
    assert lines[0].startswith("plugin_id,")


def test_plugins_export_rejects_unknown_format(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    runner.invoke(app, ["instance", "use", "dev"])
    result = runner.invoke(
        app,
        ["plugins", "export", "--format", "xml", "--out", str(tmp_path / "x")],
    )
    assert result.exit_code != 0


def test_plugins_no_subcommand_shows_parent_detail_and_subcommand_guide(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "dev", (_info("com.snc.incident"),))
    runner.invoke(app, ["instance", "use", "dev"])
    # Widen the runner terminal so CommandGuide rows aren't truncated.
    result = runner.invoke(app, ["plugins"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    # Box 1: parent detail panel
    assert "nexus plugins" in result.output
    assert "Purpose:" in result.output
    assert "Example:" in result.output
    # Box 2: subcommand listing
    assert "list" in result.output
    assert "info" in result.output
    assert "export" in result.output


def test_list_emits_json_when_format_flag_provided(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "list", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert "plugins" in payload  # PluginInventory shape
    assert any(p["plugin_id"] == "com.x" for p in payload["plugins"])


def test_list_errors_on_unknown_format_value(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "list", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output


def test_info_emits_json_when_format_flag_provided(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "info", "com.x", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert payload["plugin_id"] == "com.x"


def test_info_errors_on_unknown_format_value(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "info", "com.x", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output
