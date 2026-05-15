# tests/test_cli_plugins_updates_apply.py
# Tests for `nexus plugins updates` --family / --apply / --out flags.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the batch-upgrade extensions on `nexus plugins updates`."""

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


def test_plugins_updates_unknown_family_exits_2_and_lists_available(
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
    result = runner.invoke(app, ["plugins", "updates", "--family", "BOGUS"])
    assert result.exit_code == 2
    assert "ITSM" in result.output
    assert "ITOM" in result.output
    assert "BOGUS" in result.output


def test_plugins_updates_apply_executes_batch_upgrade(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--apply --yes calls executor.batch_upgrade once with the pending set."""
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
    ) -> BatchUpgradeReport:
        del console
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
    monkeypatch.setattr("nexus.cli._acquire_token", _fake_acquire)
    monkeypatch.setattr("nexus.cli.ServiceNowClient", _fake_client)

    result = runner.invoke(app, ["plugins", "updates", "--apply", "--yes"])
    assert result.exit_code == 0
    assert len(calls) == 1
    target_ids = cast(list[str], calls[0]["targets"])
    assert set(target_ids) == {"com.acme.incident", "com.acme.cmdb"}
    assert calls[0]["families"] == ()


def test_plugins_updates_apply_writes_report_yaml(
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
    ) -> BatchUpgradeReport:
        del console, targets
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

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade", _fake_batch_upgrade
    )
    monkeypatch.setattr("nexus.cli._acquire_token", _fake_acquire)
    monkeypatch.setattr("nexus.cli.ServiceNowClient", _fake_client)

    out_path = tmp_path / "report.yaml"
    result = runner.invoke(
        app,
        [
            "plugins",
            "updates",
            "--apply",
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


def test_plugins_updates_apply_prompts_when_yes_absent(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without --yes, declining the prompt exits 0 without calling batch_upgrade."""
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])

    calls: list[int] = []

    async def _should_not_run(
        _self: object,
        _targets: tuple[PluginInfo, ...],
        *,
        families: tuple[str, ...],
        console: object,
    ) -> BatchUpgradeReport:
        del families, console
        calls.append(1)
        return BatchUpgradeReport(
            results=(), families=(), target_count=0, succeeded=0, failed=0
        )

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade", _should_not_run
    )
    result = runner.invoke(app, ["plugins", "updates", "--apply"], input="n\n")
    assert result.exit_code == 0
    assert calls == []


def test_plugins_updates_without_apply_remains_dry_run(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No --apply flag: lists the candidate set, never invokes batch_upgrade."""
    _seed(tmp_path, "prod", (_info("com.acme.incident", family="ITSM"),))
    runner.invoke(app, ["instance", "use", "prod"])

    calls: list[int] = []

    async def _should_not_run(
        _self: object,
        _targets: tuple[PluginInfo, ...],
        *,
        families: tuple[str, ...],
        console: object,
    ) -> BatchUpgradeReport:
        del families, console
        calls.append(1)
        return BatchUpgradeReport(
            results=(), families=(), target_count=0, succeeded=0, failed=0
        )

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade", _should_not_run
    )
    result = runner.invoke(app, ["plugins", "updates"])
    assert result.exit_code == 0
    assert "com.acme.incident" in result.output
    assert calls == []


def test_plugins_updates_apply_empty_target_exits_zero(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No pending updates + --apply: exit 0, never invoke batch_upgrade."""
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

    async def _should_not_run(
        _self: object,
        _targets: tuple[PluginInfo, ...],
        *,
        families: tuple[str, ...],
        console: object,
    ) -> BatchUpgradeReport:
        del families, console
        calls.append(1)
        return BatchUpgradeReport(
            results=(), families=(), target_count=0, succeeded=0, failed=0
        )

    monkeypatch.setattr(
        "nexus.plugins.executor.PluginExecutor.batch_upgrade", _should_not_run
    )
    result = runner.invoke(app, ["plugins", "updates", "--apply", "--yes"])
    assert result.exit_code == 0
    assert calls == []
    assert "Nothing to upgrade" in result.output
