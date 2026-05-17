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


@pytest.mark.asyncio
async def test_rescan_plugin_inventory_saves_fresh_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A successful rescan persists the new PluginInventory via the registry."""
    from nexus.cli.views import _rescan_plugin_inventory  # noqa: PLC0415
    from nexus.instances.registry import InstanceRegistry  # noqa: PLC0415

    _seed(tmp_path, "prod", (_info("com.x"),))
    registry = InstanceRegistry(tmp_path / "instances")
    new_inventory = PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=(_info("com.fresh"),),
    )

    async def _fake_scan(
        _self: object, _url: str, _token: str, _sn_version: str, *, capture_counts: bool = True
    ) -> PluginInventory:
        del capture_counts
        return new_inventory

    monkeypatch.setattr("nexus.plugins.scanner.PluginScanner.scan", _fake_scan)
    await _rescan_plugin_inventory(_meta("prod"), "tok", registry)
    persisted = registry.load_plugin_inventory("prod")
    assert persisted is not None
    assert tuple(p.plugin_id for p in persisted.plugins) == ("com.fresh",)


def test_dependencies_panel_with_empty_id_rows_returns_no_prereqs_notice() -> None:
    """When SN only returns degenerate rows, the panel shows a clear notice.

    Prior bug: the panel rendered ``Plugin: None`` because SN's response had
    a single row with a null ``Id``. The filtered panel now returns a
    Notice with "No prerequisite plugins ..." text instead.
    """
    from nexus.cli.renderables import dependencies_panel as _dependencies_panel  # noqa: PLC0415
    from nexus.plugins.dependencies import DependencyEntry  # noqa: PLC0415
    from nexus.ui.components.notice import Notice  # noqa: PLC0415

    deps = (
        DependencyEntry(
            id="",
            orig_string="",
            type="Plugin",
            min_version="",
            source_app_id="",
            installed=True,
            active=True,
            hide_on_ui=False,
            status="Installed",
            status_value="installed",
            order=0,
            link="",
            has_license=False,
            is_allowed_install=True,
        ),
    )
    panel = _dependencies_panel(deps, "sn_grc_infosec")
    assert isinstance(panel, Notice)
    assert "No prerequisite plugins" in panel.message
    assert "sn_grc_infosec" in panel.message


def test_dependencies_panel_filters_hide_on_ui_rows() -> None:
    """Rows SN marks as hide_on_ui are filtered out of the user-facing panel."""
    from nexus.cli.renderables import dependencies_panel as _dependencies_panel  # noqa: PLC0415
    from nexus.plugins.dependencies import DependencyEntry  # noqa: PLC0415
    from nexus.ui.components.notice import Notice  # noqa: PLC0415

    def _entry(id_: str, hide: bool) -> DependencyEntry:
        return DependencyEntry(
            id=id_,
            orig_string="",
            type="Plugin",
            min_version="1.0.0",
            source_app_id="x",
            installed=False,
            active=False,
            hide_on_ui=hide,
            status="Will be Installed",
            status_value="will_be_installed",
            order=0,
            link="",
            has_license=True,
            is_allowed_install=True,
        )

    deps = (_entry("internal_helper", hide=True),)
    panel = _dependencies_panel(deps, "sn_grc_infosec")
    assert isinstance(panel, Notice), "all-hidden cascade should collapse to notice"


def test_cascade_actionable_drops_empty_id_and_hidden_rows() -> None:
    """Filter keeps only rows the user can act on."""
    from nexus.cli.renderables import cascade_actionable as _cascade_actionable  # noqa: PLC0415
    from nexus.plugins.dependencies import DependencyEntry  # noqa: PLC0415

    def _e(id_: str, hide: bool) -> DependencyEntry:
        return DependencyEntry(
            id=id_,
            orig_string=f"{id_}:1.0",
            type="Plugin",
            min_version="1.0",
            source_app_id="x",
            installed=False,
            active=False,
            hide_on_ui=hide,
            status="Will be Installed",
            status_value="will_be_installed",
            order=0,
            link="",
            has_license=True,
            is_allowed_install=True,
        )

    deps = (_e("sn_vul", False), _e("", False), _e("hidden", True))
    out = _cascade_actionable(deps)
    assert tuple(d.id for d in out) == ("sn_vul",)


def test_cascade_scope_extracts_scope_from_orig_string() -> None:
    """orig_string of the form ``scope:version`` yields the scope."""
    from nexus.cli.renderables import cascade_scope as _cascade_scope  # noqa: PLC0415
    from nexus.plugins.dependencies import DependencyEntry  # noqa: PLC0415

    entry = DependencyEntry(
        id="Display Name",
        orig_string="sn_vul:30.3.4",
        type="Plugin",
        min_version="30.0.0",
        source_app_id="x",
        installed=True,
        active=True,
        hide_on_ui=False,
        status="Will be Updated",
        status_value="will_be_updated",
        order=1,
        link="",
        has_license=True,
        is_allowed_install=True,
    )
    assert _cascade_scope(entry) == "sn_vul"


def test_cascade_scope_falls_back_to_id_when_orig_string_missing() -> None:
    """Without a colon-delimited orig_string we fall back to the display id."""
    from nexus.cli.renderables import cascade_scope as _cascade_scope  # noqa: PLC0415
    from nexus.plugins.dependencies import DependencyEntry  # noqa: PLC0415

    entry = DependencyEntry(
        id="bare_id",
        orig_string="",
        type="Plugin",
        min_version="",
        source_app_id="",
        installed=False,
        active=False,
        hide_on_ui=False,
        status="",
        status_value="",
        order=0,
        link="",
        has_license=False,
        is_allowed_install=False,
    )
    assert _cascade_scope(entry) == "bare_id"


def test_cascade_summary_notice_lists_scopes_with_count() -> None:
    """The summary notice mentions the count and every cascade scope id."""
    from nexus.cli.renderables import (  # noqa: PLC0415
        cascade_summary_notice as _cascade_summary_notice,
    )
    from nexus.plugins.dependencies import DependencyEntry  # noqa: PLC0415

    def _e(scope: str) -> DependencyEntry:
        return DependencyEntry(
            id=scope.upper(),
            orig_string=f"{scope}:1.0",
            type="Plugin",
            min_version="1.0",
            source_app_id="x",
            installed=False,
            active=False,
            hide_on_ui=False,
            status="Will be Updated",
            status_value="will_be_updated",
            order=0,
            link="",
            has_license=True,
            is_allowed_install=True,
        )

    actionable = (_e("sn_vul"), _e("sn_sec_cmn"))
    notice = _cascade_summary_notice(actionable, "sn_vul_patch_orch")
    assert "sn_vul_patch_orch" in notice.message
    assert "2 plugin" in notice.message
    assert "sn_vul" in notice.message
    assert "sn_sec_cmn" in notice.message


def test_dependencies_panel_renders_actionable_rows() -> None:
    """Real prerequisite rows survive the filter and render in the table."""
    from nexus.cli.renderables import dependencies_panel as _dependencies_panel  # noqa: PLC0415
    from nexus.plugins.dependencies import DependencyEntry  # noqa: PLC0415
    from nexus.ui.components.table import DataTable  # noqa: PLC0415

    deps = (
        DependencyEntry(
            id="Performance Analytics",
            orig_string="com.snc.pa:8.0.0",
            type="Application",
            min_version="8.0.0",
            source_app_id="pa",
            installed=True,
            active=True,
            hide_on_ui=False,
            status="Will be Updated",
            status_value="will_be_updated",
            order=1,
            link="",
            has_license=True,
            is_allowed_install=True,
        ),
    )
    panel = _dependencies_panel(deps, "sn_pa_designer")
    assert isinstance(panel, DataTable)
    assert "sn_pa_designer" in panel.title
    assert len(panel.rows) == 1


@pytest.mark.asyncio
async def test_rescan_plugin_inventory_warns_on_failure_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scan exceptions are caught: helper returns None, inventory stays untouched."""
    from nexus.cli.views import _rescan_plugin_inventory  # noqa: PLC0415
    from nexus.instances.registry import InstanceRegistry  # noqa: PLC0415

    _seed(tmp_path, "prod", (_info("com.old"),))
    registry = InstanceRegistry(tmp_path / "instances")

    async def _failing_scan(
        _self: object, _url: str, _token: str, _sn_version: str, *, capture_counts: bool = True
    ) -> PluginInventory:
        del capture_counts
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr("nexus.plugins.scanner.PluginScanner.scan", _failing_scan)
    await _rescan_plugin_inventory(_meta("prod"), "tok", registry)
    persisted = registry.load_plugin_inventory("prod")
    assert persisted is not None
    assert tuple(p.plugin_id for p in persisted.plugins) == ("com.old",)
