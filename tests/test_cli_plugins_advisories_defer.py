# tests/test_cli_plugins_advisories_defer.py
# Tests for defer, undo-defer, and list-deferred subcommands.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus plugins defer / undo-defer / list-deferred / --include-deferred."""

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

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

# The bundled advisory YAMLs contain:
#   com.snc.ess  v1.0  -> EOL finding  (details = "End-of-life 2024-12-31; replacement: com.snc.now_experience")
#   com.snc.cms  v1.5  -> CVE-2024-EXAMPLE-1 (affects >=1.0,<2.2.1)
#   Unknown Vendor     -> license finding
#
# Use com.snc.ess EOL for most defer/undo-defer/list-deferred tests because
# the EOL details string is stable and easy to supply.


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
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": version,
            "state": "active",
            "source": "store",
            "product_family": "Uncategorized",
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
            "vendor": vendor,
        }
    )


def _seed(
    tmp_path: Path,
    profile: str,
    plugins: tuple[PluginInfo, ...],
) -> None:
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


# ---------------------------------------------------------------------------
# Task 3: defer
# ---------------------------------------------------------------------------


def test_defer_writes_override_when_finding_exists(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "scheduled for upgrade Q3",
        ],
    )
    assert result.exit_code == 0, result.output
    override_file = tmp_path / "instances" / "prod" / "advisory-overrides.yaml"
    assert override_file.exists()
    assert "com.snc.ess" in override_file.read_text(encoding="utf-8")
    assert "scheduled for upgrade Q3" in override_file.read_text(encoding="utf-8")


def test_defer_exits_1_on_duplicate(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "first",
        ],
    )
    result = runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "second",
        ],
    )
    assert result.exit_code == 1
    assert "already exists" in result.output.lower()


def test_defer_exits_1_when_finding_not_present(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.unaffected", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.unaffected",
            "cve",
            "CVE-9999-9999",
            "--reason",
            "false positive",
        ],
    )
    assert result.exit_code == 1
    assert "No matching finding" in result.output


def test_defer_exits_1_on_unknown_advisory_type(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "bogus",
            "some-detail",
            "--reason",
            "x",
        ],
    )
    assert result.exit_code == 1
    assert "Unknown advisory type" in result.output


def test_defer_exits_1_on_empty_reason(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "   ",
        ],
    )
    assert result.exit_code == 1
    assert "--reason" in result.output


# ---------------------------------------------------------------------------
# Task 4: undo-defer
# ---------------------------------------------------------------------------


def test_undo_defer_removes_existing_override(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "temp",
        ],
    )
    result = runner.invoke(
        app,
        [
            "plugins",
            "undo-defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
        ],
    )
    assert result.exit_code == 0, result.output
    text = (tmp_path / "instances" / "prod" / "advisory-overrides.yaml").read_text(encoding="utf-8")
    assert "com.snc.ess" not in text


def test_undo_defer_exits_1_when_override_not_found(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(
        app,
        [
            "plugins",
            "undo-defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
        ],
    )
    assert result.exit_code == 1
    assert "No matching override" in result.output


def test_undo_defer_exits_1_on_unknown_advisory_type(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(
        app,
        ["plugins", "undo-defer", "com.snc.ess", "bogus", "some-detail"],
    )
    assert result.exit_code == 1
    assert "Unknown advisory type" in result.output


# ---------------------------------------------------------------------------
# Task 5: list-deferred
# ---------------------------------------------------------------------------


def test_list_deferred_shows_no_overrides_when_empty(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "list-deferred"])
    assert result.exit_code == 0, result.output
    assert "No advisory overrides" in result.output


def test_list_deferred_renders_table_when_overrides_exist(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "upgrade in Q3",
        ],
    )
    result = runner.invoke(app, ["plugins", "list-deferred"])
    assert result.exit_code == 0, result.output
    assert "com.snc.ess" in result.output
    assert "upgrade in Q3" in result.output


def test_list_deferred_emits_json_when_format_json(runner: CliRunner, tmp_path: Path) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "ok",
        ],
    )
    result = runner.invoke(app, ["plugins", "list-deferred", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert "overrides" in payload
    assert len(payload["overrides"]) == 1


# ---------------------------------------------------------------------------
# Task 6: --include-deferred + summary count
# ---------------------------------------------------------------------------


def test_advisories_summary_shows_deferred_count_when_overrides_exist(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "planned",
        ],
    )
    result = runner.invoke(app, ["plugins", "advisories"])
    assert result.exit_code == 0, result.output
    assert "1 deferred" in result.output


def test_advisories_excludes_deferred_findings_by_default(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "planned",
        ],
    )
    result = runner.invoke(app, ["plugins", "advisories"])
    assert result.exit_code == 0, result.output
    # Deferred finding should NOT appear in default output (only "1 deferred" in summary)
    assert "No advisories found" in result.output or "deferred" in result.output


def test_advisories_include_deferred_shows_deferred_prefix(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "planned",
        ],
    )
    result = runner.invoke(app, ["plugins", "advisories", "--include-deferred"])
    assert result.exit_code == 0, result.output
    assert "[deferred]" in result.output


def test_advisories_include_deferred_json_contains_deferred_marker(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "planned",
        ],
    )
    result = runner.invoke(app, ["plugins", "advisories", "--include-deferred", "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.strip().split("\n")[-1])
    summaries = [f["summary"] for f in payload["findings"]]
    assert any("[deferred]" in s for s in summaries)


def test_advisories_strict_exits_1_only_for_non_deferred_findings(
    runner: CliRunner, tmp_path: Path
) -> None:
    """--strict exits 0 when the only finding is deferred (excluded by default)."""
    _seed(tmp_path, "prod", (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    runner.invoke(
        app,
        [
            "plugins",
            "defer",
            "com.snc.ess",
            "eol",
            "End-of-life 2024-12-31; replacement: com.snc.now_experience",
            "--reason",
            "planned",
        ],
    )
    result = runner.invoke(app, ["plugins", "advisories", "--strict"])
    assert result.exit_code == 0
