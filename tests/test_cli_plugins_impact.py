# tests/test_cli_plugins_impact.py
# Tests for the nexus plugins impact command.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus plugins impact."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.instances.registry import InstanceRegistry
from nexus.plugins.models import PluginInfo, PluginInventory, ScopeRecordCount

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


def _ok_stats_payload() -> dict[str, object]:
    return {
        "result": [
            {
                "stats": {"count": "42"},
                "groupby_fields": [{"field": "sys_class_name", "value": "sys_script"}],
            }
        ]
    }


def _patch_token_and_stats(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stats_status: int = 200,
    stats_payload: dict[str, object] | None = None,
) -> None:
    """Stub _acquire_token and route Aggregate API through a MockTransport."""

    def fake_acquire(profile: str) -> tuple[InstanceRegistry, InstanceMeta, str, datetime]:
        paths = NexusPaths.from_env()
        registry = InstanceRegistry(paths.instances_dir)
        meta = registry.load(profile if profile else "prod")
        return registry, meta, "fake-token", datetime.now(UTC)

    monkeypatch.setattr("nexus.cli._acquire_token", fake_acquire)

    payload = stats_payload if stats_payload is not None else _ok_stats_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(stats_status, json=payload)

    monkeypatch.setattr("nexus.cli._impact_transport", lambda: httpx.MockTransport(handler))


def test_impact_renders_reverse_deps_and_counts_tables(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.target"),
            _info("com.dependent", depends_on=("com.target",)),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 0
    assert "Reverse dependencies" in result.output
    assert "com.dependent" in result.output
    assert "sys_script" in result.output
    assert "42" in result.output


def test_impact_prints_no_dependents_message_when_none(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 0
    assert "No plugins depend on com.target" in result.output


def test_impact_warns_when_record_counts_unavailable(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.target"),
            _info("com.dependent", depends_on=("com.target",)),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch, stats_status=500)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 0
    assert "Record counts unavailable" in result.output
    assert "com.dependent" in result.output


def test_impact_errors_when_plugin_not_in_inventory(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.other"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 1
    assert "Plugin not found" in result.output


def test_impact_warns_when_inventory_missing(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", None)
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 1
    assert "nexus instance refresh" in result.output


def test_impact_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.target"),
            _info("com.dep", depends_on=("com.target",)),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(app, ["plugins", "impact", "com.target", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert payload["target_plugin_id"] == "com.target"
    assert "reverse_deps" in payload


def test_impact_errors_on_unknown_format_value(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(app, ["plugins", "impact", "com.target", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output


def test_plugins_impact_default_uses_cache(
    tmp_path: Path,
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default invocation serves from cached record_counts without hitting stats/sys_metadata."""
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("nexus.cli._impact_transport", lambda: transport)

    cached_info = _info("com.target").model_copy(
        update={"record_counts": (ScopeRecordCount(table="sys_script", count=42),)}
    )
    _seed(tmp_path, "dev", (cached_info,))

    def fake_acquire(profile: str) -> tuple[InstanceRegistry, InstanceMeta, str, datetime]:
        paths = NexusPaths.from_env()
        registry = InstanceRegistry(paths.instances_dir)
        meta = registry.load(profile if profile else "dev")
        return registry, meta, "t", datetime.now(UTC)

    monkeypatch.setattr("nexus.cli._acquire_token", fake_acquire)

    result = runner.invoke(app, ["plugins", "impact", "com.target", "--instance", "dev"])
    assert result.exit_code == 0
    assert stats_calls == []


def test_plugins_impact_live_flag_passes_through(
    tmp_path: Path,
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--live forces a fresh stats/sys_metadata call even when cache is populated."""
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "stats": {"count": "99"},
                            "groupby_fields": [{"field": "sys_class_name", "value": "sys_script"}],
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("nexus.cli._impact_transport", lambda: transport)

    cached_info = _info("com.target").model_copy(
        update={"record_counts": (ScopeRecordCount(table="sys_script", count=1),)}
    )
    _seed(tmp_path, "dev", (cached_info,))

    def fake_acquire(profile: str) -> tuple[InstanceRegistry, InstanceMeta, str, datetime]:
        paths = NexusPaths.from_env()
        registry = InstanceRegistry(paths.instances_dir)
        meta = registry.load(profile if profile else "dev")
        return registry, meta, "t", datetime.now(UTC)

    monkeypatch.setattr("nexus.cli._acquire_token", fake_acquire)

    result = runner.invoke(app, ["plugins", "impact", "com.target", "--instance", "dev", "--live"])
    assert result.exit_code == 0
    assert len(stats_calls) == 1


def _cross_scope_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch _impact_transport and _acquire_token with cross-scope-aware mock."""

    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(200, json={"result": [{"name": "target_table"}]})
        if "sys_dictionary" in req.url.path:
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "name": "other_table",
                            "element": "ref_field",
                            "sys_scope.scope": "com.other",
                        }
                    ]
                },
            )
        if "/api/now/stats/other_table" in req.url.path:
            return httpx.Response(200, json={"result": {"stats": {"count": "99"}}})
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(200, json={"result": []})

    monkeypatch.setattr("nexus.cli._impact_transport", lambda: httpx.MockTransport(handler))


def _fake_acquire(profile: str) -> tuple[InstanceRegistry, InstanceMeta, str, datetime]:
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta = registry.load(profile if profile else "prod")
    return registry, meta, "fake-token", datetime.now(UTC)


def test_impact_renders_cross_scope_refs_table_when_refs_exist(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _cross_scope_transport(monkeypatch)
    monkeypatch.setattr("nexus.cli._acquire_token", _fake_acquire)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 0
    assert "Cross-scope references" in result.output
    assert "other_table" in result.output
    assert "com.other" in result.output


def test_impact_no_cross_scope_flag_omits_refs_table(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _cross_scope_transport(monkeypatch)
    monkeypatch.setattr("nexus.cli._acquire_token", _fake_acquire)
    result = runner.invoke(app, ["plugins", "impact", "com.target", "--no-cross-scope"])
    assert result.exit_code == 0
    assert "Cross-scope references" not in result.output


def test_impact_summary_includes_cross_scope_count_when_refs_exist(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _cross_scope_transport(monkeypatch)
    monkeypatch.setattr("nexus.cli._acquire_token", _fake_acquire)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 0
    assert "cross-scope refs" in result.output


def test_impact_warns_when_cross_scope_unavailable_and_not_opted_out(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When cross-scope scan fails (not opted out), warn the user."""

    def handler(req: httpx.Request) -> httpx.Response:
        if "sys_db_object" in req.url.path:
            return httpx.Response(500, json={})
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(200, json={"result": []})

    monkeypatch.setattr("nexus.cli._impact_transport", lambda: httpx.MockTransport(handler))
    monkeypatch.setattr("nexus.cli._acquire_token", _fake_acquire)
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 0
    assert "Cross-scope refs unavailable" in result.output
