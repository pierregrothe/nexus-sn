# tests/test_cli_plugins_advisories.py
# Tests for the nexus plugins advisories command.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for nexus plugins advisories."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.plugins.errors import PluginAdvisoryDataError
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
    vendor: str = "",
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
            "vendor": vendor,
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


# Plugins exercised against the BUNDLED advisory YAMLs:
#   com.snc.ess              -> EOL "end_of_life 2024-12-31" (past) -> HIGH
#   com.snc.cms              -> CVE-2024-EXAMPLE-1 affects >=1.0,<2.2.1 -> HIGH
#   "Unknown Vendor"         -> license unknown-vendor (allow-list non-empty) -> MEDIUM


def test_advisories_renders_three_sections_when_findings_in_each(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.snc.ess", version="1.0", vendor="ServiceNow"),
            _info("com.snc.cms", version="1.5", vendor="ServiceNow"),
            _info("com.weird.tool", version="1.0", vendor="Unknown Vendor"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories"])
    assert result.exit_code == 0
    assert "EOL" in result.output
    assert "CVE" in result.output
    assert "License" in result.output
    assert "advisory finding" in result.output


def test_advisories_prints_no_findings_when_clean(runner: CliRunner, tmp_path: Path) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.unaffected", version="1.0", vendor="ServiceNow"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories"])
    assert result.exit_code == 0
    assert "No advisories found" in result.output


def test_advisories_filters_by_type_when_type_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.snc.ess", version="1.0", vendor="ServiceNow"),
            _info("com.snc.cms", version="1.5", vendor="ServiceNow"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories", "--type", "cve"])
    assert result.exit_code == 0
    assert "CVE" in result.output
    assert "EOL plugins" not in result.output


def test_advisories_filters_by_severity_when_severity_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.snc.ess", version="1.0", vendor="ServiceNow"),
            _info("com.weird.tool", version="1.0", vendor="Unknown Vendor"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories", "--severity", "high"])
    assert result.exit_code == 0
    # Unknown-vendor finding is MEDIUM; --severity high filters it out.
    assert "Unknown Vendor" not in result.output


def test_advisories_renders_per_severity_counts_in_trailing_notice(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.snc.ess", version="1.0", vendor="ServiceNow"),
            _info("com.weird.tool", version="1.0", vendor="Unknown Vendor"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories"])
    assert result.exit_code == 0
    assert "critical" in result.output
    assert "high" in result.output
    assert "medium" in result.output


def test_advisories_warns_when_inventory_missing(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", None)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories"])
    assert result.exit_code != 0
    assert "nexus instance refresh" in result.output


def test_advisories_errors_when_data_files_corrupted(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),),
    )

    def _raise_load() -> object:
        raise PluginAdvisoryDataError("simulated corruption")

    monkeypatch.setattr("nexus.cli.AdvisoryDatabase.load", staticmethod(_raise_load))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories"])
    assert result.exit_code == 1
    assert "Advisory data corrupted" in result.output
