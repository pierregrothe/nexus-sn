# tests/test_plugins_batch_upgrade.py
# Tests for PluginExecutor.batch_upgrade and BatchUpgradeReport.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for the batch upgrade workflow."""

from datetime import UTC, datetime
from typing import Any

import pytest
from rich.console import Console

from nexus.plugins.executor import (
    BatchUpgradeReport,
    OperationResult,
    PluginExecutor,
)
from nexus.plugins.models import PluginInfo, PluginInventory
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []


def _info(
    pid: str,
    *,
    version: str = "1.0.0",
    latest_version: str | None = "2.0.0",
    family: str = "ITSM",
) -> PluginInfo:
    return PluginInfo(
        plugin_id=pid,
        name=pid,
        version=version,
        state="active",
        source="store",
        product_family=family,
        depends_on=(),
        sys_id=f"sysid-{pid}",
        installed_at=None,
        latest_version=latest_version,
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )


def _upgrade_kickoff(tracker: str = "t1") -> dict[str, Any]:
    return {
        "status": "0",
        "status_label": "Pending",
        "percent_complete": 0,
        "error": "",
        "update_set": None,
        "rollback_version": None,
        "trackerId": tracker,
        "status_message": "",
        "status_detail": "",
    }


def _progress(status: str, pct: int, err: str = "", tracker: str = "t1") -> dict[str, Any]:
    return {
        "status": status,
        "status_label": "x",
        "percent_complete": pct,
        "error": err,
        "update_set": None,
        "rollback_version": None,
        "trackerId": tracker,
        "status_message": "",
        "status_detail": "",
    }


@pytest.fixture
def console() -> Console:
    return Console(record=True, width=120)


def test_batch_upgrade_report_exit_code_all_succeeded() -> None:
    report = BatchUpgradeReport(
        results=(),
        families=(),
        target_count=0,
        succeeded=0,
        failed=0,
    )
    assert report.exit_code == 0


def test_batch_upgrade_report_exit_code_with_failures() -> None:
    fake_result = OperationResult(
        action="upgrade",
        plugin_id="com.acme.x",
        success=False,
        message="boom",
        duration_s=0.1,
        tracker_id="t1",
        update_set=None,
        rollback_version=None,
    )
    report = BatchUpgradeReport(
        results=(fake_result,),
        families=("ITSM",),
        target_count=1,
        succeeded=0,
        failed=1,
    )
    assert report.exit_code == 1


async def test_batch_upgrade_all_succeed_in_order(console: Console) -> None:
    client = FakeServiceNowClient()
    for tracker in ("t-a", "t-b", "t-c"):
        client.queue_upgrade_response(_upgrade_kickoff(tracker))
        client.set_progress_sequence(tracker, [_progress("2", 100, tracker=tracker)])
    inv = _inventory(
        _info("com.acme.a"),
        _info("com.acme.b"),
        _info("com.acme.c"),
    )
    executor = PluginExecutor(client=client, inventory=inv)

    targets = inv.plugins
    report = await executor.batch_upgrade(targets, families=(), console=console)

    assert report.target_count == 3
    assert report.succeeded == 3
    assert report.failed == 0
    assert tuple(r.plugin_id for r in report.results) == (
        "com.acme.a",
        "com.acme.b",
        "com.acme.c",
    )
    assert all(r.success for r in report.results)
    assert report.exit_code == 0
