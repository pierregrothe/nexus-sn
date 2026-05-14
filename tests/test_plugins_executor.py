# tests/test_plugins_executor.py
# Tests for PluginExecutor lifecycle (Tasks 8 + 9).
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for PluginExecutor construction, inventory refresh, and install."""

from datetime import UTC, datetime
from typing import Any

import pytest
from rich.console import Console

from nexus.plugins import progress as _progress_module
from nexus.plugins.diff import PromoteAction, PromotionPlan
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


@pytest.mark.asyncio
async def test_activate_returns_success_result(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.x", state="inactive"))
    client.queue_activate_response(_install_response("act-1"))
    client.set_progress_sequence("act-1", [_progress("2", 100, tracker="act-1")])
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.activate("com.x")
    assert result.success
    assert result.action == "activate"
    assert result.plugin_id == "com.x"


@pytest.mark.asyncio
async def test_activate_unknown_plugin_returns_failure(client: FakeServiceNowClient) -> None:
    inv = _inventory()  # empty
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.activate("com.nope")
    assert not result.success
    assert "com.nope" in result.message
    assert result.action == "activate"


@pytest.mark.asyncio
async def test_upgrade_returns_rollback_version(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.x"))
    client.queue_upgrade_response(_install_response("up-1"))
    # Final progress carries the rollback_version from SN
    final_progress = _progress("2", 100, tracker="up-1")
    final_progress["rollback_version"] = "1.4"
    client.set_progress_sequence("up-1", [final_progress])
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.upgrade("com.x", target_version="2.0")
    assert result.success
    assert result.rollback_version == "1.4"
    assert result.action == "upgrade"


@pytest.mark.asyncio
async def test_upgrade_unknown_plugin_returns_failure(client: FakeServiceNowClient) -> None:
    inv = _inventory()
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.upgrade("com.nope")
    assert not result.success
    assert result.action == "upgrade"


@pytest.mark.asyncio
async def test_apply_plan_executes_actions_in_stable_order(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.b", state="inactive"))
    plan = PromotionPlan(
        source_profile="dev", target_profile="prod",
        actions=(
            PromoteAction(action="install", plugin_id="com.a", name="com.a",
                          product_family="ITSM", target_version="1.0", current_version=None),
            PromoteAction(action="activate", plugin_id="com.b", name="com.b",
                          product_family="ITSM", target_version="1.0", current_version=None),
            PromoteAction(action="upgrade", plugin_id="com.b", name="com.b",
                          product_family="ITSM", target_version="2.0", current_version="1.0"),
        ),
    )
    # Seed inventory for com.a so install can find sys_id via lookup
    inv = _inventory(_info("com.a"), _info("com.b", state="inactive"))
    client.queue_install_response(_install_response("t-i"))
    client.queue_activate_response(_install_response("t-a"))
    client.queue_upgrade_response(_install_response("t-u"))
    client.set_progress_sequence("t-i", [_progress("2", 100, tracker="t-i")])
    client.set_progress_sequence("t-a", [_progress("2", 100, tracker="t-a")])
    client.set_progress_sequence("t-u", [_progress("2", 100, tracker="t-u")])
    client._tables["v_plugin"] = [{"name": "com.a", "sys_id": "ai", "version": "1.0", "state": "active"}]

    exe = PluginExecutor(client=client, inventory=inv)
    log = await exe.apply_plan(plan, console=Console(quiet=True))
    assert log.success_count == 3
    assert log.failure_count == 0
    actions = tuple(r.action for r in log.results)
    assert actions == ("install", "activate", "upgrade")


@pytest.mark.asyncio
async def test_apply_plan_rejects_unknown_plugin_for_activate(client: FakeServiceNowClient) -> None:
    inv = _inventory()  # empty
    plan = PromotionPlan(
        source_profile="dev", target_profile="prod",
        actions=(
            PromoteAction(action="activate", plugin_id="com.nope", name="com.nope",
                          product_family="ITSM", target_version="1.0", current_version=None),
        ),
    )
    exe = PluginExecutor(client=client, inventory=inv)
    with pytest.raises(PluginNotFoundError):
        await exe.apply_plan(plan, console=Console(quiet=True))


@pytest.mark.asyncio
async def test_apply_plan_rollback_on_install_failure(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.a"), _info("com.b", state="inactive"))
    plan = PromotionPlan(
        source_profile="dev", target_profile="prod",
        actions=(
            PromoteAction(action="install", plugin_id="com.a", name="com.a",
                          product_family="ITSM", target_version="1.0", current_version=None),
            PromoteAction(action="activate", plugin_id="com.b", name="com.b",
                          product_family="ITSM", target_version="1.0", current_version=None),
        ),
    )
    # install com.a succeeds
    client.queue_install_response(_install_response("t1"))
    client.set_progress_sequence("t1", [_progress("2", 100, tracker="t1")])
    client._tables["v_plugin"] = [{"name": "com.a", "sys_id": "ai", "version": "1.0", "state": "active"}]
    # activate com.b fails
    client.queue_activate_response(_install_response("t2"))
    client.set_progress_sequence("t2", [_progress("3", 50, err="boom", tracker="t2")])
    # rollback of "install com.a" -> submit_install (uninstall placeholder until sub-project N)
    client.queue_install_response(_install_response("rb-1"))
    client.set_progress_sequence("rb-1", [_progress("2", 100, tracker="rb-1")])

    exe = PluginExecutor(client=client, inventory=inv)
    log = await exe.apply_plan(plan, console=Console(quiet=True))
    actions = tuple(r.action for r in log.results)
    # install ok, activate failed, rollback_install for com.a
    assert actions[0] == "install"
    assert actions[1] == "activate"
    assert actions[2] == "rollback_install"
    assert log.failure_count >= 1  # at least the failed activate


@pytest.mark.asyncio
async def test_rollback_continues_through_secondary_failures(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.a"), _info("com.c"), _info("com.b", state="inactive"))
    plan = PromotionPlan(
        source_profile="dev", target_profile="prod",
        actions=(
            PromoteAction(action="install", plugin_id="com.a", name="com.a",
                          product_family="ITSM", target_version="1.0", current_version=None),
            PromoteAction(action="install", plugin_id="com.c", name="com.c",
                          product_family="ITSM", target_version="1.0", current_version=None),
            PromoteAction(action="activate", plugin_id="com.b", name="com.b",
                          product_family="ITSM", target_version="1.0", current_version=None),
        ),
    )
    # Two installs succeed
    client.queue_install_response(_install_response("ti1"))
    client.queue_install_response(_install_response("ti2"))
    client.set_progress_sequence("ti1", [_progress("2", 100, tracker="ti1")])
    client.set_progress_sequence("ti2", [_progress("2", 100, tracker="ti2")])
    client._tables["v_plugin"] = [
        {"name": "com.a", "sys_id": "a", "version": "1.0", "state": "active"},
        {"name": "com.c", "sys_id": "c", "version": "1.0", "state": "active"},
    ]
    # Activate fails
    client.queue_activate_response(_install_response("ta"))
    client.set_progress_sequence("ta", [_progress("3", 0, err="x", tracker="ta")])
    # First rollback (for com.c -- LIFO) has NO response queued -> fails
    # Second rollback (for com.a) has a response queued -> succeeds
    client.queue_install_response(_install_response("rb-a"))
    client.set_progress_sequence("rb-a", [_progress("2", 100, tracker="rb-a")])

    exe = PluginExecutor(client=client, inventory=inv)
    log = await exe.apply_plan(plan, console=Console(quiet=True))
    # 3 forward results + 2 rollback entries
    assert len(log.results) == 5
    rb_results = [r for r in log.results if r.action.startswith("rollback_")]
    assert len(rb_results) == 2
    # One rollback succeeded, one failed (LIFO: com.c rollback first which fails)
    successes = sum(1 for r in rb_results if r.success)
    failures = sum(1 for r in rb_results if not r.success)
    assert successes == 1
    assert failures == 1
