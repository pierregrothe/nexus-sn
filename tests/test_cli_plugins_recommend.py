# tests/test_cli_plugins_recommend.py
# Tests for plugins recommend deactivate, plugins explain, plugins roadmap.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus plugins recommend deactivate, explain, and roadmap commands."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from nexus.api.errors import AnthropicError
from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.instances.registry import InstanceRegistry
from nexus.plugins.models import PluginInfo, PluginInventory
from nexus.plugins.recommendations import EXPLAIN_SYSTEM_PROMPT
from tests.fakes.fake_agent_client import FakeAgentClient

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
    state: str = "active",
    depends_on: tuple[str, ...] = (),
    record_counts: tuple[object, ...] = (),
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
            "record_counts": record_counts,
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


def _patch_agent(monkeypatch: pytest.MonkeyPatch, fake: FakeAgentClient) -> None:
    """Replace _agent_client_factory with one returning fake."""
    monkeypatch.setattr("nexus.cli._agent_client_factory", lambda: fake)


def _patch_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub _acquire_token to return a fake token from local registry."""

    def fake_acquire(
        profile: str,
    ) -> tuple[InstanceRegistry, InstanceMeta, str, datetime]:
        paths = NexusPaths.from_env()
        registry = InstanceRegistry(paths.instances_dir)
        meta = registry.load(profile if profile else "prod")
        return registry, meta, "fake-token", datetime.now(UTC)

    monkeypatch.setattr("nexus.cli._acquire_token", fake_acquire)


def _patch_token_and_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub _acquire_token and set a pass-through MockTransport."""
    _patch_token(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": []})

    monkeypatch.setattr("nexus.cli._impact_transport", lambda: httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# recommend deactivate
# ---------------------------------------------------------------------------


def test_recommend_deactivate_calls_llm_and_prints_response(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Plant an orphan: no depends_on, empty record_counts
    _seed(tmp_path, "prod", (_info("com.orphan"),))
    runner.invoke(app, ["instance", "use", "prod"])
    fake = FakeAgentClient(canned_response="### Top candidates\n- com.orphan (safe to remove)")
    _patch_agent(monkeypatch, fake)
    result = runner.invoke(app, ["plugins", "recommend", "deactivate"])
    assert result.exit_code == 0
    assert "Top candidates" in result.output
    assert len(fake.calls) == 1
    assert "com.orphan" in fake.calls[0]["prompt"]


def test_recommend_deactivate_instance_flag_routes_profile(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "dev", (_info("com.orphan"),))
    fake = FakeAgentClient(canned_response="FAKE")
    _patch_agent(monkeypatch, fake)
    result = runner.invoke(app, ["plugins", "recommend", "deactivate", "--instance", "dev"])
    assert result.exit_code == 0
    assert "FAKE" in result.output


def test_recommend_deactivate_short_circuits_when_no_orphans_or_advisories(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # record_counts=None -> uncaptured -> total_records returns None -> not an orphan
    # Empty vendor -> no license advisory; plugin not in EOL/CVE data
    _seed(tmp_path, "prod", (PluginInfo.model_validate({
        "plugin_id": "com.well.used",
        "name": "com.well.used",
        "version": "1.0",
        "state": "active",
        "source": "store",
        "product_family": "Uncategorized",
        "depends_on": (),
        "sys_id": "sys-well",
        "installed_at": None,
        "record_counts": None,
    }),))
    runner.invoke(app, ["instance", "use", "prod"])
    fake = FakeAgentClient()
    _patch_agent(monkeypatch, fake)
    result = runner.invoke(app, ["plugins", "recommend", "deactivate"])
    assert result.exit_code == 0
    assert "nothing to recommend" in result.output.lower()
    assert len(fake.calls) == 0


def test_recommend_deactivate_exits_1_on_anthropic_error(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.orphan"),))
    runner.invoke(app, ["instance", "use", "prod"])
    fake = FakeAgentClient(side_effect=AnthropicError(500, "overloaded"))
    _patch_agent(monkeypatch, fake)
    result = runner.invoke(app, ["plugins", "recommend", "deactivate"])
    assert result.exit_code == 1
    assert "AI request failed" in result.output


# ---------------------------------------------------------------------------
# plugins explain
# ---------------------------------------------------------------------------


def test_plugins_explain_prints_llm_response(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_transport(monkeypatch)
    fake = FakeAgentClient(canned_response="## What it does\nManages CMDB.")
    _patch_agent(monkeypatch, fake)
    result = runner.invoke(app, ["plugins", "explain", "com.target"])
    assert result.exit_code == 0
    assert "What it does" in result.output
    assert len(fake.calls) == 1


def test_plugins_explain_uses_explain_system_prompt(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_transport(monkeypatch)
    fake = FakeAgentClient(canned_response="ok")
    _patch_agent(monkeypatch, fake)
    runner.invoke(app, ["plugins", "explain", "com.target"])
    assert fake.calls[0]["system"] == EXPLAIN_SYSTEM_PROMPT


def test_plugins_explain_exits_1_when_plugin_not_found(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.other"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_transport(monkeypatch)
    fake = FakeAgentClient()
    _patch_agent(monkeypatch, fake)
    result = runner.invoke(app, ["plugins", "explain", "com.missing"])
    assert result.exit_code == 1
    assert "Plugin not found" in result.output
    assert len(fake.calls) == 0


def test_plugins_explain_exits_1_on_anthropic_error(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_transport(monkeypatch)
    fake = FakeAgentClient(side_effect=AnthropicError(429, "rate limited"))
    _patch_agent(monkeypatch, fake)
    result = runner.invoke(app, ["plugins", "explain", "com.target"])
    assert result.exit_code == 1
    assert "AI request failed" in result.output


# ---------------------------------------------------------------------------
# plugins roadmap
# ---------------------------------------------------------------------------


def test_plugins_roadmap_prints_llm_response(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # com.snc.ess has EOL advisory -> findings are non-empty -> roadmap runs
    _seed(
        tmp_path,
        "prod",
        (_info("com.snc.ess"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    fake = FakeAgentClient(canned_response="1. Action: deactivate com.snc.ess (EOL)")
    _patch_agent(monkeypatch, fake)
    result = runner.invoke(app, ["plugins", "roadmap"])
    assert result.exit_code == 0
    assert "Action:" in result.output
    assert len(fake.calls) == 1


def test_plugins_roadmap_deferred_count_passed_to_context(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # com.snc.ess triggers an advisory, ensuring roadmap doesn't short-circuit
    _seed(tmp_path, "prod", (_info("com.snc.ess"),))
    runner.invoke(app, ["instance", "use", "prod"])
    fake = FakeAgentClient(canned_response="roadmap text")
    _patch_agent(monkeypatch, fake)
    runner.invoke(app, ["plugins", "roadmap"])
    assert len(fake.calls) == 1
    # deferred_count is 0 (no overrides seeded), confirm it appears in prompt
    assert "Deferred overrides" in fake.calls[0]["prompt"]


def test_plugins_roadmap_short_circuits_when_nothing_to_remediate(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # record_counts=None -> uncaptured -> not an orphan; clean plugin -> no advisory
    _seed(tmp_path, "prod", (PluginInfo.model_validate({
        "plugin_id": "com.well.used",
        "name": "com.well.used",
        "version": "1.0",
        "state": "active",
        "source": "store",
        "product_family": "Uncategorized",
        "depends_on": (),
        "sys_id": "sys-well",
        "installed_at": None,
        "record_counts": None,
    }),))
    runner.invoke(app, ["instance", "use", "prod"])
    fake = FakeAgentClient()
    _patch_agent(monkeypatch, fake)
    result = runner.invoke(app, ["plugins", "roadmap"])
    assert result.exit_code == 0
    assert "Nothing to remediate" in result.output
    assert len(fake.calls) == 0


def test_plugins_roadmap_exits_1_on_anthropic_error(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.snc.ess"),))
    runner.invoke(app, ["instance", "use", "prod"])
    fake = FakeAgentClient(side_effect=AnthropicError(500, "server error"))
    _patch_agent(monkeypatch, fake)
    result = runner.invoke(app, ["plugins", "roadmap"])
    assert result.exit_code == 1
    assert "AI request failed" in result.output
