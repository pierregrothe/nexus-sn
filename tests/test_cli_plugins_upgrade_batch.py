# tests/test_cli_plugins_upgrade_batch.py
# Tests for `nexus plugins upgrade` batch mode (no PLUGIN_ID + optional --family / --out).
# Author: Pierre Grothe
# Date: 2026-05-16
"""Tests for the brew-style batch-upgrade path on `nexus plugins upgrade`.

`nexus plugins upgrade` with no PLUGIN_ID upgrades every pending plugin;
``--family X`` filters the batch to one or more families. Single-plugin
mode (`nexus plugins upgrade <id>`) is exercised separately in
``test_cli_plugins_execute.py``.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
import yaml as _yaml
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.plugins.executor import BatchUpgradeReport, OperationResult
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


class _FakeAsyncCtx:
    """Stand-in for ServiceNowClient's async-context-manager API in CLI tests."""

    async def __aenter__(self) -> _FakeAsyncCtx:
        return self

    async def __aexit__(self, *_a: object) -> bool:
        return False


def _fake_client(**_kw: object) -> _FakeAsyncCtx:
    """Replacement for ServiceNowClient() construction in CLI tests."""
    return _FakeAsyncCtx()


def _fake_acquire(profile: str) -> tuple[object, object, str, object]:
    """Replacement for _acquire_token in CLI tests; only the token (3rd) matters."""
    return (profile, "url", "token", None)


def _recording_unreachable_batch(
    calls: list[int],
) -> Callable[..., Awaitable[BatchUpgradeReport]]:
    """Build an async fake of PluginExecutor.batch_upgrade that records each call.

    The returned coroutine appends to ``calls`` and returns an empty
    BatchUpgradeReport. Tests that monkeypatch batch_upgrade with this
    factory can assert ``calls == []`` to prove the method was never invoked
    (e.g. when the user declines confirmation or the target set is empty).
    """

    async def _fake(
        _self: object,
        _targets: tuple[PluginInfo, ...],
        *,
        families: tuple[str, ...],
        console: object,
        on_plugin_start: object = None,
        on_plugin_progress: object = None,
        on_plugin_complete: object = None,
    ) -> BatchUpgradeReport:
        del families, console, on_plugin_start, on_plugin_progress, on_plugin_complete
        calls.append(1)
        return BatchUpgradeReport(results=(), families=(), target_count=0, succeeded=0, failed=0)

    return _fake


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_plugins_upgrade_with_unknown_family_exits_2_and_lists_available(
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
    result = runner.invoke(app, ["plugins", "upgrade", "--family", "BOGUS"])
    assert result.exit_code == 2
    assert "ITSM" in result.output
    assert "ITOM" in result.output
    assert "BOGUS" in result.output


def test_plugins_upgrade_batch_executes_batch_upgrade(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bare `upgrade --yes` calls executor.batch_upgrade with the pending set."""
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.acme.incident", family="ITSM"),
            _info("com.acme.cmdb", family="ITOM"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])

    calls: list[dict[str, object]] = []

    async def _fake_batch_upgrade(
        _self: object,
        targets: tuple[PluginInfo, ...],
        *,
        families: tuple[str, ...],
        console: object,
        on_plugin_start: object = None,
        on_plugin_progress: object = None,
        on_plugin_complete: object = None,
    ) -> BatchUpgradeReport:
        del console, on_plugin_start, on_plugin_progress, on_plugin_complete
        calls.append({"targets": [p.plugin_id for p in targets], "families": families})
        return BatchUpgradeReport(
            results=(),
            families=families,
            target_count=0,
            succeeded=0,
            failed=0,
        )

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade",
        _fake_batch_upgrade,
    )
    monkeypatch.setattr("nexus.cli.commands_plugins_exec._acquire_token", _fake_acquire)
    monkeypatch.setattr("nexus.cli.commands_plugins_exec.ServiceNowClient", _fake_client)

    result = runner.invoke(app, ["plugins", "upgrade", "--yes"])
    assert result.exit_code == 0
    assert len(calls) == 1
    target_ids = cast(list[str], calls[0]["targets"])
    assert set(target_ids) == {"com.acme.incident", "com.acme.cmdb"}
    assert calls[0]["families"] == ()


def test_plugins_upgrade_batch_writes_report_yaml(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])

    async def _fake_batch_upgrade(
        _self: object,
        targets: tuple[PluginInfo, ...],
        *,
        families: tuple[str, ...],
        console: object,
        on_plugin_start: object = None,
        on_plugin_progress: object = None,
        on_plugin_complete: object = None,
    ) -> BatchUpgradeReport:
        del console, on_plugin_start, on_plugin_progress, on_plugin_complete, targets
        return BatchUpgradeReport(
            results=(
                OperationResult(
                    action="upgrade",
                    plugin_id="com.acme.incident",
                    success=True,
                    message="Success",
                    duration_s=1.23,
                    tracker_id="t-a",
                    update_set=None,
                    rollback_version=None,
                ),
            ),
            families=families,
            target_count=1,
            succeeded=1,
            failed=0,
        )

    monkeypatch.setattr("nexus.plugins.executor.PluginExecutor.batch_upgrade", _fake_batch_upgrade)
    monkeypatch.setattr("nexus.cli.commands_plugins_exec._acquire_token", _fake_acquire)
    monkeypatch.setattr("nexus.cli.commands_plugins_exec.ServiceNowClient", _fake_client)

    out_path = tmp_path / "report.yaml"
    result = runner.invoke(
        app,
        [
            "plugins",
            "upgrade",
            "--yes",
            "--out",
            str(out_path),
        ],
    )
    assert result.exit_code == 0
    payload = _yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert payload["target_count"] == 1
    assert payload["succeeded"] == 1
    assert payload["failed"] == 0
    assert payload["results"][0]["plugin_id"] == "com.acme.incident"
    assert payload["results"][0]["success"] is True


def test_plugins_upgrade_batch_prompts_when_yes_absent(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --yes, declining the prompt exits 0 without calling batch_upgrade."""
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])

    calls: list[int] = []
    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade",
        _recording_unreachable_batch(calls),
    )
    result = runner.invoke(app, ["plugins", "upgrade"], input="n\n")
    assert result.exit_code == 0
    assert calls == []


def test_plugins_upgrade_batch_with_empty_pending_exits_zero(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No pending updates + bare upgrade: exit 0, never invoke batch_upgrade."""
    _seed(
        tmp_path,
        "prod",
        (
            _info(
                "com.acme.incident",
                version="2.0.0",
                latest_version="2.0.0",
                family="ITSM",
            ),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])

    calls: list[int] = []
    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade",
        _recording_unreachable_batch(calls),
    )
    result = runner.invoke(app, ["plugins", "upgrade", "--yes"])
    assert result.exit_code == 0
    assert calls == []
    assert "Nothing to upgrade" in result.output


def test_plugins_upgrade_all_flag_executes_batch_upgrade(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`upgrade --all --yes` behaves like bare `upgrade --yes` (everything pending)."""
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.acme.incident", family="ITSM"),
            _info("com.acme.cmdb", family="ITOM"),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])

    calls: list[dict[str, object]] = []

    async def _fake_batch_upgrade(
        _self: object,
        targets: tuple[PluginInfo, ...],
        *,
        families: tuple[str, ...],
        console: object,
        on_plugin_start: object = None,
        on_plugin_progress: object = None,
        on_plugin_complete: object = None,
    ) -> BatchUpgradeReport:
        del console, on_plugin_start, on_plugin_progress, on_plugin_complete
        calls.append({"targets": [p.plugin_id for p in targets], "families": families})
        return BatchUpgradeReport(
            results=(),
            families=families,
            target_count=0,
            succeeded=0,
            failed=0,
        )

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade",
        _fake_batch_upgrade,
    )
    monkeypatch.setattr("nexus.cli.commands_plugins_exec._acquire_token", _fake_acquire)
    monkeypatch.setattr("nexus.cli.commands_plugins_exec.ServiceNowClient", _fake_client)

    result = runner.invoke(app, ["plugins", "upgrade", "--all", "--yes"])
    assert result.exit_code == 0
    assert len(calls) == 1
    target_ids = cast(list[str], calls[0]["targets"])
    assert set(target_ids) == {"com.acme.incident", "com.acme.cmdb"}


def test_plugins_upgrade_with_all_and_id_rejects(runner: CliRunner, tmp_path: Path) -> None:
    """--all with PLUGIN_ID is a usage error and exits 2."""
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "upgrade", "com.acme.incident", "--all"])
    assert result.exit_code == 2
    assert "--all" in result.output


def test_plugins_upgrade_with_all_and_family_rejects(runner: CliRunner, tmp_path: Path) -> None:
    """--all with --family is a usage error and exits 2."""
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "upgrade", "--all", "--family", "ITSM"])
    assert result.exit_code == 2
    assert "--all" in result.output


def test_plugins_upgrade_with_id_and_family_rejects(runner: CliRunner, tmp_path: Path) -> None:
    """PLUGIN_ID + --family is a usage error and exits 2."""
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "upgrade", "com.acme.incident", "--family", "ITSM"])
    assert result.exit_code == 2
    assert "--family" in result.output


def test_plugins_upgrade_with_to_but_no_id_rejects(runner: CliRunner, tmp_path: Path) -> None:
    """--to without PLUGIN_ID is a usage error and exits 2."""
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "upgrade", "--to", "9.9.9"])
    assert result.exit_code == 2
    assert "--to" in result.output


def test_plugins_upgrade_with_out_and_id_rejects(runner: CliRunner, tmp_path: Path) -> None:
    """--out with PLUGIN_ID is a usage error and exits 2."""
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(
        app,
        ["plugins", "upgrade", "com.acme.incident", "--out", str(tmp_path / "r.yaml")],
    )
    assert result.exit_code == 2
    assert "--out" in result.output
