# tests/test_cli_plugins_upgrade_interactive.py
# InteractiveRequiredError exit-2 + make_batch_progress wiring tests.
# Author: Pierre Grothe
# Date: 2026-05-18

"""Tests for the PLAIN-profile interactive-required guard on
``nexus plugins upgrade`` and the InteractiveRequiredError class.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.cli.errors import InteractiveRequiredError
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.plugins.executor import BatchUpgradeReport
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _seed(tmp_path: Path) -> None:
    meta = InstanceMeta.create(
        profile="prod",
        url="https://prod.service-now.com",
        username="admin",
        client_id="cid",
        sn_version="Xanadu",
        sn_build="04-01-2025_1200",
        instance_name="prod",
        token_expires_in=1800,
    )
    profile_dir = tmp_path / "instances" / "prod"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    plugin = PluginInfo.model_validate(
        {
            "plugin_id": "com.x",
            "name": "com.x",
            "version": "1.0",
            "state": "active",
            "source": "store",
            "product_family": "ITSM",
            "depends_on": (),
            "sys_id": "sys-x",
            "installed_at": None,
            "latest_version": "2.0",
        }
    )
    inv = PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=(plugin,),
    )
    (profile_dir / "plugins.json").write_text(inv.model_dump_json(indent=2), encoding="utf-8")


def test_interactive_required_error_exit_code_is_two() -> None:
    """The exception's exit_code attribute matches typer usage-error convention."""
    assert InteractiveRequiredError.exit_code == 2


def test_interactive_required_error_carries_message() -> None:
    """The exception carries a human message like any RuntimeError."""
    err = InteractiveRequiredError("interactive prompt suppressed under PLAIN")
    assert "interactive" in str(err)


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


class _FakeAsyncCtx:
    async def __aenter__(self) -> _FakeAsyncCtx:
        return self

    async def __aexit__(self, *_a: object) -> bool:
        return False


def _fake_client(**_kw: object) -> _FakeAsyncCtx:
    return _FakeAsyncCtx()


def _fake_acquire(profile: str) -> tuple[object, object, str, object]:
    return (profile, "url", "token", None)


def test_plugins_upgrade_bare_without_yes_under_plain_exits_two(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bare `upgrade` (no --yes) under PLAIN profile (CliRunner) exits 2."""
    _seed(tmp_path)
    runner.invoke(app, ["instance", "use", "prod"])
    monkeypatch.setattr("nexus.cli.commands_plugins_exec._acquire_token", _fake_acquire)
    result = runner.invoke(app, ["plugins", "upgrade"])
    assert result.exit_code == 2


def test_plugins_upgrade_with_yes_under_plain_bypasses_interactive_guard(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`upgrade --yes` under PLAIN bypasses the guard and calls batch_upgrade."""
    _seed(tmp_path)
    runner.invoke(app, ["instance", "use", "prod"])
    monkeypatch.setattr("nexus.cli.commands_plugins_exec._acquire_token", _fake_acquire)
    monkeypatch.setattr("nexus.cli.commands_plugins_exec.ServiceNowClient", _fake_client)

    async def _fake_batch_upgrade(
        _self: object,
        targets: tuple[PluginInfo, ...],
        *,
        families: tuple[str, ...] = (),
        console: object,
        on_plugin_start: object = None,
        on_plugin_progress: object = None,
        on_plugin_complete: object = None,
        progress: object = None,
    ) -> BatchUpgradeReport:
        del console, on_plugin_start, on_plugin_progress, on_plugin_complete, progress
        return BatchUpgradeReport(
            results=(),
            families=families,
            target_count=0,
            succeeded=0,
            failed=0,
        )

    monkeypatch.setattr("nexus.plugins.executor.PluginExecutor.batch_upgrade", _fake_batch_upgrade)

    async def _fake_rescan(*_a: object, **_kw: object) -> None:
        return None

    monkeypatch.setattr("nexus.cli.commands_plugins_exec._rescan_plugin_inventory", _fake_rescan)

    result = runner.invoke(app, ["plugins", "upgrade", "--yes"])
    assert result.exit_code == 0
