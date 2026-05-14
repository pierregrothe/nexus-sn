# tests/test_plugins_executor.py
# Tests for PluginExecutor lifecycle (Tasks 8 + 9).
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for PluginExecutor construction, inventory refresh, and install."""

from datetime import UTC, datetime
from typing import Any

import pytest

from nexus.plugins import progress as _progress_module
from nexus.plugins.errors import PluginNotFoundError
from nexus.plugins.executor import PluginExecutor
from nexus.plugins.models import PluginInfo, PluginInventory
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []


def _info(pid: str, *, state: str = "active") -> PluginInfo:
    return PluginInfo(
        plugin_id=pid, name=pid, version="1.0",
        state="active" if state == "active" else "inactive",
        source="servicenow", product_family="ITSM", depends_on=(),
        sys_id=f"sysid-{pid}", installed_at=None,
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=plugins,
    )


def _install_response(tracker: str = "t1") -> dict[str, Any]:
    return {
        "status": "0", "status_label": "Pending", "status_message": "",
        "status_detail": "", "error": "", "percent_complete": 0,
        "update_set": None, "rollback_version": None, "trackerId": tracker,
        "links": {"progress": {"id": tracker, "url": f"/api/sn_appclient/appmanager/progress/{tracker}"}},
    }


def _progress(status: str, pct: int, err: str = "", tracker: str = "t1") -> dict[str, Any]:
    return {
        "status": status, "status_label": "x", "percent_complete": pct,
        "error": err, "update_set": None, "rollback_version": None,
        "trackerId": tracker, "status_message": "", "status_detail": "",
    }


@pytest.fixture
def client() -> FakeServiceNowClient:
    return FakeServiceNowClient()


def test_constructor_snapshots_inventory_map(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.a"), _info("com.b"))
    exe = PluginExecutor(client=client, inventory=inv)
    assert exe.has_plugin("com.a")
    assert exe.has_plugin("com.b")
    assert not exe.has_plugin("com.z")


def test_constructor_raises_on_invalid_inventory_type(client: FakeServiceNowClient) -> None:
    with pytest.raises(TypeError):
        PluginExecutor(client=client, inventory="not an inventory")  # pyright: ignore[reportArgumentType]


def test_lookup_raises_for_unknown_plugin(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.a"))
    exe = PluginExecutor(client=client, inventory=inv)
    with pytest.raises(PluginNotFoundError) as excinfo:
        exe.lookup("com.nope")
    assert excinfo.value.plugin_id == "com.nope"


@pytest.mark.asyncio
async def test_refresh_after_install_adds_new_plugin(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.a"))
    exe = PluginExecutor(client=client, inventory=inv)
    # Seed v_plugin row that the targeted refresh will fetch
    client._tables.setdefault("v_plugin", []).append({
        "name": "com.newly_installed", "sys_id": "newsysid",
        "version": "1.0", "state": "active",
    })
    await exe._refresh_one("com.newly_installed")
    assert exe.has_plugin("com.newly_installed")


@pytest.mark.asyncio
async def test_install_returns_success_result(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.x"))
    client.queue_install_response(_install_response("t1"))
    client.set_progress_sequence("t1", [_progress("1", 50, tracker="t1"),
                                         _progress("2", 100, tracker="t1")])
    client._tables["v_plugin"] = [{
        "name": "com.x", "sys_id": "sid", "version": "1.0", "state": "active"
    }]
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.install("com.x", version="1.0")
    assert result.success
    assert result.action == "install"
    assert result.plugin_id == "com.x"
    assert result.tracker_id == "t1"


@pytest.mark.asyncio
async def test_install_failure_returns_unsuccessful_result(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.x"))
    client.queue_install_response(_install_response("t2"))
    client.set_progress_sequence("t2", [_progress("3", 80, err="dep missing", tracker="t2")])
    exe = PluginExecutor(client=client, inventory=inv)
    # Use a short poll interval to keep the test fast
    monkey_was = _progress_module.DEFAULT_POLL_INTERVAL_S
    _progress_module.DEFAULT_POLL_INTERVAL_S = 0.01
    try:
        result = await exe.install("com.x")
    finally:
        _progress_module.DEFAULT_POLL_INTERVAL_S = monkey_was
    assert not result.success
    assert "dep missing" in result.message


@pytest.mark.asyncio
async def test_install_unknown_plugin_returns_failure(client: FakeServiceNowClient) -> None:
    inv = _inventory()  # empty
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.install("com.nope")
    assert not result.success
    assert "com.nope" in result.message
