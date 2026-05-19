# tests/test_executor_progress_kwarg.py
# Tests for the new BatchProgressProtocol kwarg on upgrade + batch_upgrade.
# Author: Pierre Grothe
# Date: 2026-05-18

"""Tests for :meth:`PluginExecutor.upgrade` and :meth:`batch_upgrade`
``progress`` kwarg routing.

Uses :class:`FakeBatchProgress` to record method calls. Covers the
happy success path, failure path, and that ``progress=None`` preserves
today's behaviour exactly.
"""

from datetime import UTC, datetime
from typing import Any

import pytest
from rich.console import Console

from nexus.plugins.executor import PluginExecutor
from nexus.plugins.models import PluginInfo, PluginInventory
from tests.fakes.batch_progress import FakeBatchProgress
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []


def _info(pid: str, *, latest: str = "2.0") -> PluginInfo:
    return PluginInfo(
        plugin_id=pid,
        name=pid,
        version="1.0",
        latest_version=latest,
        state="active",
        source="store",
        product_family="ITSM",
        depends_on=(),
        sys_id=f"sysid-{pid}",
        installed_at=None,
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )


def _install_response(tracker: str = "t1") -> dict[str, Any]:
    return {
        "status": "0",
        "status_label": "Pending",
        "status_message": "",
        "status_detail": "",
        "error": "",
        "percent_complete": 0,
        "update_set": None,
        "rollback_version": None,
        "trackerId": tracker,
        "links": {
            "progress": {"id": tracker, "url": f"/api/sn_appclient/appmanager/progress/{tracker}"}
        },
    }


def _progress_payload(status: str, pct: int, tracker: str = "t1") -> dict[str, Any]:
    return {
        "status": status,
        "status_label": "x",
        "percent_complete": pct,
        "error": "",
        "update_set": None,
        "rollback_version": None,
        "trackerId": tracker,
        "status_message": "",
        "status_detail": "",
    }


@pytest.fixture
def client() -> FakeServiceNowClient:
    return FakeServiceNowClient()


@pytest.mark.asyncio
async def test_upgrade_with_progress_kwarg_records_start_and_finish_success(
    client: FakeServiceNowClient,
) -> None:
    inv = _inventory(_info("com.x"))
    client.queue_upgrade_response(_install_response("up-1"))
    client.set_progress_sequence("up-1", [_progress_payload("2", 100, "up-1")])
    bp = FakeBatchProgress()
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.upgrade("com.x", target_version="2.0", progress=bp)
    assert result.success is True
    names = [name for name, _ in bp.recorded_calls]
    assert names[0] == "start_item"
    assert names[-1] == "finish_item"
    finish_kwargs = bp.recorded_calls[-1][1]
    assert finish_kwargs["success"] is True
    assert finish_kwargs["family"] == "ITSM"


@pytest.mark.asyncio
async def test_upgrade_with_progress_kwarg_records_update_on_poll(
    client: FakeServiceNowClient,
) -> None:
    inv = _inventory(_info("com.x"))
    client.queue_upgrade_response(_install_response("up-1"))
    client.set_progress_sequence(
        "up-1",
        [
            _progress_payload("1", 33, "up-1"),
            _progress_payload("1", 66, "up-1"),
            _progress_payload("2", 100, "up-1"),
        ],
    )
    bp = FakeBatchProgress()
    exe = PluginExecutor(client=client, inventory=inv)
    await exe.upgrade("com.x", target_version="2.0", progress=bp)
    update_pcts = [kwargs["sn_pct"] for name, kwargs in bp.recorded_calls if name == "update_item"]
    assert 33 in update_pcts
    assert 66 in update_pcts


@pytest.mark.asyncio
async def test_upgrade_with_progress_kwarg_records_finish_failure(
    client: FakeServiceNowClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    inv = _inventory(_info("com.x"))

    async def _raise(
        _self: object, _sys_id: str, _ver: str | None = None, **_kw: object
    ) -> dict[str, Any]:
        raise RuntimeError("submit failed")

    monkeypatch.setattr(FakeServiceNowClient, "submit_upgrade", _raise)
    bp = FakeBatchProgress()
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.upgrade("com.x", target_version="2.0", progress=bp)
    assert result.success is False
    finish_kwargs = bp.recorded_calls[-1][1]
    assert bp.recorded_calls[-1][0] == "finish_item"
    assert finish_kwargs["success"] is False


@pytest.mark.asyncio
async def test_upgrade_without_progress_preserves_existing_behavior(
    client: FakeServiceNowClient,
) -> None:
    inv = _inventory(_info("com.x"))
    client.queue_upgrade_response(_install_response("up-1"))
    client.set_progress_sequence("up-1", [_progress_payload("2", 100, "up-1")])
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.upgrade("com.x", target_version="2.0")
    assert result.success is True
    assert result.message == "x"


@pytest.mark.asyncio
async def test_batch_upgrade_with_progress_calls_start_batch_once(
    client: FakeServiceNowClient,
) -> None:
    inv = _inventory(_info("com.x"), _info("com.y"))
    client.queue_upgrade_response(_install_response("u-x"))
    client.queue_upgrade_response(_install_response("u-y"))
    client.set_progress_sequence("u-x", [_progress_payload("2", 100, "u-x")])
    client.set_progress_sequence("u-y", [_progress_payload("2", 100, "u-y")])
    bp = FakeBatchProgress()
    exe = PluginExecutor(client=client, inventory=inv)
    console = Console(record=True)
    await exe.batch_upgrade(inv.plugins, console=console, progress=bp)
    start_batch_calls = [n for n, _ in bp.recorded_calls if n == "start_batch"]
    assert len(start_batch_calls) == 1
    assert bp.recorded_calls[0] == ("start_batch", {"total": 2})


@pytest.mark.asyncio
async def test_batch_upgrade_with_progress_skip_on_fail_records_failure_then_continues(
    client: FakeServiceNowClient,
) -> None:
    inv = _inventory(_info("com.x"), _info("com.y"))
    client.queue_upgrade_response(_install_response("u-x"))
    client.queue_upgrade_response(_install_response("u-y"))
    client.set_progress_sequence("u-x", [_progress_payload("3", 100, "u-x")])  # status 3 = failure
    client.set_progress_sequence("u-y", [_progress_payload("2", 100, "u-y")])
    bp = FakeBatchProgress()
    exe = PluginExecutor(client=client, inventory=inv)
    console = Console(record=True)
    report = await exe.batch_upgrade(inv.plugins, console=console, progress=bp)
    assert report.succeeded == 1
    assert report.failed == 1
    finish_outcomes = [
        kwargs["success"] for name, kwargs in bp.recorded_calls if name == "finish_item"
    ]
    assert finish_outcomes == [False, True]


@pytest.mark.asyncio
async def test_batch_upgrade_without_progress_preserves_existing_behavior(
    client: FakeServiceNowClient,
) -> None:
    inv = _inventory(_info("com.x"))
    client.queue_upgrade_response(_install_response("u-x"))
    client.set_progress_sequence("u-x", [_progress_payload("2", 100, "u-x")])
    exe = PluginExecutor(client=client, inventory=inv)
    console = Console(record=True, force_terminal=True)
    report = await exe.batch_upgrade(inv.plugins, console=console)
    assert report.succeeded == 1
    captured = console.export_text()
    assert "upgrade com.x" in captured
