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
        plugin_id=pid,
        name=pid,
        version="1.0",
        state="active" if state == "active" else "inactive",
        source="servicenow",
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
        PluginExecutor(
            client=client, inventory="not an inventory"
        )  # pyright: ignore[reportArgumentType]


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
    client._tables.setdefault("v_plugin", []).append(
        {
            "name": "com.newly_installed",
            "sys_id": "newsysid",
            "version": "1.0",
            "state": "active",
        }
    )
    await exe._refresh_one("com.newly_installed")
    assert exe.has_plugin("com.newly_installed")


@pytest.mark.asyncio
async def test_install_returns_success_result(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.x"))
    client.queue_install_response(_install_response("t1"))
    client.set_progress_sequence(
        "t1", [_progress("1", 50, tracker="t1"), _progress("2", 100, tracker="t1")]
    )
    client._tables["v_plugin"] = [
        {"name": "com.x", "sys_id": "sid", "version": "1.0", "state": "active"}
    ]
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
async def test_upgrade_returns_success_when_submit_raises_already_installed(
    client: FakeServiceNowClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SN can refuse at the submit phase with HTTP 400 'already installed'.

    brew/apt convention: ``upgrade`` against an already-up-to-date package is
    a silent no-op, not a failure.
    """
    inv = _inventory(_info("com.x"))

    async def _raise_already_installed(
        _self: object, _sys_id: str, _ver: str | None
    ) -> dict[str, Any]:
        raise RuntimeError("Application version is currently installed (Http Response: 400)")

    monkeypatch.setattr(FakeServiceNowClient, "submit_upgrade", _raise_already_installed)

    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.upgrade("com.x", target_version="2.0")
    assert result.success
    assert result.action == "upgrade"
    assert "Already at target version" in result.message
    assert result.tracker_id == ""


@pytest.mark.asyncio
async def test_upgrade_returns_success_when_progress_reports_already_installed(
    client: FakeServiceNowClient,
) -> None:
    """SN 'already installed' usually surfaces from the progress poll, not submit.

    Real PDI behaviour: SN accepts the upgrade submission with HTTP 200 and a
    tracker id, then the progress tracker terminates with status=3 and
    error='Application version is currently installed (Http Response: 400)'.
    Regression for the path the user actually hit during a family batch.
    """
    inv = _inventory(_info("com.x"))
    client.queue_upgrade_response(_install_response("up-x"))
    client.set_progress_sequence(
        "up-x",
        [
            _progress(
                "3",
                100,
                err="Application version is currently installed (Http Response: 400)",
                tracker="up-x",
            )
        ],
    )
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.upgrade("com.x", target_version="2.0")
    assert result.success
    assert result.action == "upgrade"
    assert "Already at target version" in result.message
    assert result.tracker_id == "up-x"


@pytest.mark.asyncio
async def test_install_returns_success_when_progress_reports_already_installed(
    client: FakeServiceNowClient,
) -> None:
    """Same 'already installed' coverage for install via the progress poll."""
    inv = _inventory(_info("com.x"))
    client.queue_install_response(_install_response("in-x"))
    client.set_progress_sequence(
        "in-x",
        [
            _progress(
                "3",
                100,
                err="Application version is currently installed (Http Response: 400)",
                tracker="in-x",
            )
        ],
    )
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.install("com.x", version="1.0")
    assert result.success
    assert result.action == "install"
    assert "Already installed at target version" in result.message
    assert result.tracker_id == "in-x"


@pytest.mark.asyncio
async def test_install_returns_success_when_sn_reports_already_installed(
    client: FakeServiceNowClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same idempotent semantics for install: re-installing the live version is a no-op."""
    inv = _inventory(_info("com.x"))

    async def _raise_already_installed(
        _self: object, _sys_id: str, _ver: str | None
    ) -> dict[str, Any]:
        raise RuntimeError("Application version is currently installed (Http Response: 400)")

    monkeypatch.setattr(FakeServiceNowClient, "submit_install", _raise_already_installed)

    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.install("com.x", version="1.0")
    assert result.success
    assert result.action == "install"
    assert "Already installed" in result.message
    assert result.tracker_id == ""


@pytest.mark.asyncio
async def test_upgrade_returns_failure_for_unrelated_400_error(
    client: FakeServiceNowClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Other 400-class errors stay failures -- the already-installed match must be exact."""
    inv = _inventory(_info("com.x"))

    async def _raise_other(_self: object, _sys_id: str, _ver: str | None) -> dict[str, Any]:
        raise RuntimeError("Unexpected HTTP 400: missing required parameter")

    monkeypatch.setattr(FakeServiceNowClient, "submit_upgrade", _raise_other)

    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.upgrade("com.x", target_version="2.0")
    assert not result.success
    assert "missing required parameter" in result.message


@pytest.mark.asyncio
async def test_upgrade_returns_failure_when_progress_poll_raises_auth_error(
    client: FakeServiceNowClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SN 401 during progress poll becomes a per-plugin OperationResult, not a crash.

    Regression: a long-running upgrade can outlive the OAuth token. When that
    happens mid-poll, batch_upgrade must continue with the next plugin instead
    of bubbling SNAuthError up and aborting the whole batch.
    """
    inv = _inventory(_info("com.x"))
    client.queue_upgrade_response(_install_response("up-auth"))

    async def _raise_auth(_self: object, _tracker_id: str) -> dict[str, Any]:
        raise RuntimeError("Authentication failed: HTTP 401")

    monkeypatch.setattr(FakeServiceNowClient, "fetch_progress", _raise_auth)

    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.upgrade("com.x", target_version="2.0")
    assert not result.success
    assert result.action == "upgrade"
    assert result.tracker_id == "up-auth"
    assert "401" in result.message


@pytest.mark.asyncio
async def test_apply_plan_executes_actions_in_stable_order(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.b", state="inactive"))
    plan = PromotionPlan(
        source_profile="dev",
        target_profile="prod",
        actions=(
            PromoteAction(
                action="install",
                plugin_id="com.a",
                name="com.a",
                product_family="ITSM",
                target_version="1.0",
                current_version=None,
            ),
            PromoteAction(
                action="activate",
                plugin_id="com.b",
                name="com.b",
                product_family="ITSM",
                target_version="1.0",
                current_version=None,
            ),
            PromoteAction(
                action="upgrade",
                plugin_id="com.b",
                name="com.b",
                product_family="ITSM",
                target_version="2.0",
                current_version="1.0",
            ),
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
    client._tables["v_plugin"] = [
        {"name": "com.a", "sys_id": "ai", "version": "1.0", "state": "active"}
    ]

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
        source_profile="dev",
        target_profile="prod",
        actions=(
            PromoteAction(
                action="activate",
                plugin_id="com.nope",
                name="com.nope",
                product_family="ITSM",
                target_version="1.0",
                current_version=None,
            ),
        ),
    )
    exe = PluginExecutor(client=client, inventory=inv)
    with pytest.raises(PluginNotFoundError):
        await exe.apply_plan(plan, console=Console(quiet=True))


@pytest.mark.asyncio
async def test_apply_plan_rollback_on_install_failure(client: FakeServiceNowClient) -> None:
    inv = _inventory(_info("com.a"), _info("com.b", state="inactive"))
    plan = PromotionPlan(
        source_profile="dev",
        target_profile="prod",
        actions=(
            PromoteAction(
                action="install",
                plugin_id="com.a",
                name="com.a",
                product_family="ITSM",
                target_version="1.0",
                current_version=None,
            ),
            PromoteAction(
                action="activate",
                plugin_id="com.b",
                name="com.b",
                product_family="ITSM",
                target_version="1.0",
                current_version=None,
            ),
        ),
    )
    # install com.a succeeds
    client.queue_install_response(_install_response("t1"))
    client.set_progress_sequence("t1", [_progress("2", 100, tracker="t1")])
    client._tables["v_plugin"] = [
        {"name": "com.a", "sys_id": "ai", "version": "1.0", "state": "active"}
    ]
    # activate com.b fails
    client.queue_activate_response(_install_response("t2"))
    client.set_progress_sequence("t2", [_progress("3", 50, err="boom", tracker="t2")])
    # rollback of "install com.a" -> submit_uninstall (real undo endpoint)
    client.queue_uninstall_response(_install_response("rb-1"))
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
        source_profile="dev",
        target_profile="prod",
        actions=(
            PromoteAction(
                action="install",
                plugin_id="com.a",
                name="com.a",
                product_family="ITSM",
                target_version="1.0",
                current_version=None,
            ),
            PromoteAction(
                action="install",
                plugin_id="com.c",
                name="com.c",
                product_family="ITSM",
                target_version="1.0",
                current_version=None,
            ),
            PromoteAction(
                action="activate",
                plugin_id="com.b",
                name="com.b",
                product_family="ITSM",
                target_version="1.0",
                current_version=None,
            ),
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
    client.queue_uninstall_response(_install_response("rb-a"))
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


@pytest.mark.asyncio
async def test_deactivate_blocked_by_local_reverse_deps(client: FakeServiceNowClient) -> None:
    """Deactivate is refused without --force when reverse-deps exist."""
    inv = _inventory(
        _info("com.a"),
        PluginInfo(
            plugin_id="com.b",
            name="com.b",
            version="1.0",
            state="active",
            source="servicenow",
            product_family="ITSM",
            depends_on=("com.a",),
            sys_id="sysid-com.b",
            installed_at=None,
        ),
    )
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.deactivate("com.a")
    assert not result.success
    assert "impact gate blocked" in result.message
    assert result.action == "deactivate"


@pytest.mark.asyncio
async def test_deactivate_force_bypasses_impact_gate(client: FakeServiceNowClient) -> None:
    """force=True skips the gate and proceeds to submit_deactivate."""
    inv = _inventory(
        _info("com.a"),
        PluginInfo(
            plugin_id="com.b",
            name="com.b",
            version="1.0",
            state="active",
            source="servicenow",
            product_family="ITSM",
            depends_on=("com.a",),
            sys_id="sysid-com.b",
            installed_at=None,
        ),
    )
    client.queue_deactivate_response(_install_response("td-1"))
    client.set_progress_sequence("td-1", [_progress("2", 100, tracker="td-1")])
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.deactivate("com.a", force=True)
    assert result.success
    assert result.action == "deactivate"


@pytest.mark.asyncio
async def test_deactivate_success_when_no_deps(client: FakeServiceNowClient) -> None:
    """When no local reverse-deps and SN returns empty cascade, deactivate works."""
    inv = _inventory(_info("com.lonely"))
    client.queue_deactivate_response(_install_response("td-2"))
    client.set_progress_sequence("td-2", [_progress("2", 100, tracker="td-2")])
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.deactivate("com.lonely")
    assert result.success


@pytest.mark.asyncio
async def test_deactivate_unknown_plugin_returns_failure(client: FakeServiceNowClient) -> None:
    """Deactivating an unknown plugin returns a failure result."""
    inv = _inventory()
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.deactivate("com.nope")
    assert not result.success
    assert "com.nope" in result.message
    assert result.action == "deactivate"


@pytest.mark.asyncio
async def test_uninstall_refused_for_base_servicenow_plugin(client: FakeServiceNowClient) -> None:
    """source=='servicenow' uninstall is refused regardless of --force."""
    inv = _inventory(_info("com.snc.incident"))
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.uninstall("com.snc.incident", force=True)
    assert not result.success
    assert "cannot be uninstalled" in result.message
    assert result.action == "uninstall"


@pytest.mark.asyncio
async def test_uninstall_succeeds_for_non_base_plugin(client: FakeServiceNowClient) -> None:
    """Non-base (store/custom) plugins can be uninstalled."""
    inv = _inventory(
        PluginInfo(
            plugin_id="com.acme.app",
            name="acme",
            version="1.0",
            state="active",
            source="store",
            product_family="ITSM",
            depends_on=(),
            sys_id="acme-sys",
            installed_at=None,
        ),
    )
    client.queue_uninstall_response(_install_response("tu-1"))
    client.set_progress_sequence("tu-1", [_progress("2", 100, tracker="tu-1")])
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.uninstall("com.acme.app")
    assert result.success
    assert result.action == "uninstall"


@pytest.mark.asyncio
async def test_uninstall_blocked_by_impact_gate(client: FakeServiceNowClient) -> None:
    """Non-base plugin with reverse-deps blocked unless --force."""
    inv = _inventory(
        PluginInfo(
            plugin_id="com.acme.app",
            name="acme",
            version="1.0",
            state="active",
            source="store",
            product_family="ITSM",
            depends_on=(),
            sys_id="acme-sys",
            installed_at=None,
        ),
        PluginInfo(
            plugin_id="com.dep",
            name="dep",
            version="1.0",
            state="active",
            source="store",
            product_family="ITSM",
            depends_on=("com.acme.app",),
            sys_id="dep-sys",
            installed_at=None,
        ),
    )
    exe = PluginExecutor(client=client, inventory=inv)
    result = await exe.uninstall("com.acme.app")
    assert not result.success
    assert "impact gate blocked" in result.message


@pytest.mark.asyncio
async def test_rollback_uses_real_uninstall_endpoint(client: FakeServiceNowClient) -> None:
    """After M->N transition, rollback of 'install' calls submit_uninstall (not submit_install)."""
    plan = PromotionPlan(
        source_profile="dev",
        target_profile="prod",
        actions=(
            PromoteAction(
                action="install",
                plugin_id="com.a",
                name="com.a",
                product_family="ITSM",
                target_version="1.0",
                current_version=None,
            ),
            PromoteAction(
                action="activate",
                plugin_id="com.b",
                name="com.b",
                product_family="ITSM",
                target_version="1.0",
                current_version=None,
            ),
        ),
    )
    inv = _inventory(_info("com.a"), _info("com.b", state="inactive"))
    # install com.a succeeds
    client.queue_install_response(_install_response("ti"))
    client.set_progress_sequence("ti", [_progress("2", 100, tracker="ti")])
    client._tables["v_plugin"] = [
        {"name": "com.a", "sys_id": "ai", "version": "1.0", "state": "active"}
    ]
    # activate com.b fails
    client.queue_activate_response(_install_response("ta"))
    client.set_progress_sequence("ta", [_progress("3", 50, err="boom", tracker="ta")])
    # rollback of 'install com.a' MUST call submit_uninstall (not submit_install)
    client.queue_uninstall_response(_install_response("rb-u"))
    client.set_progress_sequence("rb-u", [_progress("2", 100, tracker="rb-u")])

    exe = PluginExecutor(client=client, inventory=inv)
    log = await exe.apply_plan(plan, console=Console(quiet=True))
    rb = [r for r in log.results if r.action == "rollback_install"]
    assert len(rb) == 1
    assert rb[0].success
