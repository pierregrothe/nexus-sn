# tests/test_migrate_preflight.py
# Tests for the read-only `nexus migrate preflight` probe core (Story 07).
# Author: Pierre Grothe
# Date: 2026-07-02
"""Tests for nexus.migrate.preflight.run_preflight.

Fake httpx.AsyncBaseTransport per role_probe's own test pattern (no mocks,
tests/test_instance_role_probe.py). Covers AC1 (probe items) x AC2
(pass/fail/unknown status mapping per probe item), AC4 (both instances
probed, grouped, deterministic ordering), and AC5 (GET-only -- every
request issued by run_preflight uses method GET, asserted per instance).
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from nexus.migrate.models import PreflightItemResult, PreflightReport, PreflightStatus
from nexus.migrate.preflight import MIGRATE_PREFLIGHT_PROBES, run_preflight

__all__: list[str] = []

_BASE_URL = "https://test.service-now.com"


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """Build an httpx client wired to a MockTransport running ``handler``."""
    return httpx.AsyncClient(
        base_url=_BASE_URL,
        headers={"Authorization": "Bearer t", "Accept": "application/json"},
        transport=httpx.MockTransport(handler),
    )


def _plugin_row(active: object) -> httpx.Response:
    return httpx.Response(
        200, json={"result": [{"id": "com.glide.continuousdelivery", "active": active}]}
    )


def _empty_result() -> httpx.Response:
    return httpx.Response(200, json={"result": []})


def _ok_row() -> httpx.Response:
    return httpx.Response(200, json={"result": [{"sys_id": "1"}]})


def _sn_error(status: int, message: str = "", detail: str = "") -> httpx.Response:
    return httpx.Response(status, json={"error": {"message": message, "detail": detail}})


def _handler(
    *,
    v_plugin: httpx.Response | None = None,
    v_plugin_raises: Exception | None = None,
    sys_user_role: httpx.Response | None = None,
    sys_app: httpx.Response | None = None,
    methods: list[str] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Build a fake Table API handler; unset tables default to a healthy 200 row."""

    def handle(request: httpx.Request) -> httpx.Response:
        if methods is not None:
            methods.append(request.method)
        path = request.url.path
        if path == "/api/now/table/v_plugin":
            if v_plugin_raises is not None:
                raise v_plugin_raises
            return v_plugin if v_plugin is not None else _plugin_row("true")
        if path == "/api/now/table/sys_user_role":
            return sys_user_role if sys_user_role is not None else _ok_row()
        if path == "/api/now/table/sys_app":
            return sys_app if sys_app is not None else _ok_row()
        raise AssertionError(f"unexpected path: {path}")

    return handle


def _healthy_client() -> httpx.AsyncClient:
    return _client(_handler())


def _find(report: PreflightReport, *, instance: str, item: str) -> PreflightItemResult:
    for row in report.items:
        if row.instance == instance and row.item == item:
            return row
    raise AssertionError(f"no row for instance={instance!r} item={item!r}")


# -- AC1: MIGRATE_PREFLIGHT_PROBES ------------------------------------------


def test_migrate_preflight_probes_exact_set() -> None:
    assert {p.table for p in MIGRATE_PREFLIGHT_PROBES} == {"sys_user_role", "sys_app"}


# -- AC1/AC2: CICD plugin presence + active state ---------------------------


@pytest.mark.asyncio
async def test_run_preflight_cicd_plugin_pass_when_present_and_active() -> None:
    async with _client(_handler(v_plugin=_plugin_row("true"))) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="cicd-plugin")
    assert row.status is PreflightStatus.PASS
    assert row.detail == ""


@pytest.mark.asyncio
async def test_run_preflight_cicd_plugin_pass_when_active_is_json_boolean() -> None:
    async with _client(_handler(v_plugin=_plugin_row(True))) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="cicd-plugin")
    assert row.status is PreflightStatus.PASS


@pytest.mark.asyncio
async def test_run_preflight_cicd_plugin_fail_when_active_field_is_unrecognized_type() -> None:
    async with _client(_handler(v_plugin=_plugin_row(None))) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="cicd-plugin")
    assert row.status is PreflightStatus.FAIL


@pytest.mark.asyncio
async def test_run_preflight_cicd_plugin_fail_when_present_but_inactive() -> None:
    async with _client(_handler(v_plugin=_plugin_row("false"))) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="cicd-plugin")
    assert row.status is PreflightStatus.FAIL
    assert "inactive" in row.detail


@pytest.mark.asyncio
async def test_run_preflight_cicd_plugin_fail_when_absent() -> None:
    async with _client(_handler(v_plugin=_empty_result())) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="cicd-plugin")
    assert row.status is PreflightStatus.FAIL
    assert "not found" in row.detail


@pytest.mark.asyncio
async def test_run_preflight_cicd_plugin_fail_on_403() -> None:
    async with _client(_handler(v_plugin=_sn_error(403))) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="cicd-plugin")
    assert row.status is PreflightStatus.FAIL


@pytest.mark.asyncio
async def test_run_preflight_cicd_plugin_unknown_on_404() -> None:
    async with _client(_handler(v_plugin=_sn_error(404))) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="cicd-plugin")
    assert row.status is PreflightStatus.UNKNOWN


@pytest.mark.asyncio
async def test_run_preflight_cicd_plugin_unknown_on_network_error() -> None:
    handler = _handler(v_plugin_raises=httpx.ConnectError("network down"))
    async with _client(handler) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="cicd-plugin")
    assert row.status is PreflightStatus.UNKNOWN
    assert "ConnectError" in row.detail


@pytest.mark.asyncio
async def test_run_preflight_cicd_plugin_unknown_on_malformed_json() -> None:
    malformed = httpx.Response(200, text="not json")
    async with _client(_handler(v_plugin=malformed)) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="cicd-plugin")
    assert row.status is PreflightStatus.UNKNOWN
    assert "malformed" in row.detail


# -- AC1/AC2: sn_cicd role grantability --------------------------------------


@pytest.mark.asyncio
async def test_run_preflight_sn_cicd_role_pass_on_200() -> None:
    async with _healthy_client() as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="sn-cicd-role")
    assert row.status is PreflightStatus.PASS


@pytest.mark.asyncio
async def test_run_preflight_sn_cicd_role_unknown_on_403() -> None:
    # AC1 per-item override of AC2's default 403 -> FAIL: a 403 reading
    # sys_user_role means the probe could not look at the role table at
    # all -- zero evidence about the role itself, so unknown, not fail.
    handler = _handler(sys_user_role=_sn_error(403, "User Not Authorized", "needs admin"))
    async with _client(handler) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="sn-cicd-role")
    assert row.status is PreflightStatus.UNKNOWN
    assert "could not read sys_user_role" in row.detail
    assert "manually" in row.detail
    assert "needs admin" in row.detail  # SN-side detail is still appended


@pytest.mark.asyncio
async def test_run_preflight_sn_cicd_role_unknown_on_404() -> None:
    async with _client(_handler(sys_user_role=_sn_error(404))) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="sn-cicd-role")
    assert row.status is PreflightStatus.UNKNOWN


# -- AC1/AC2: App Repository entitlement -------------------------------------


@pytest.mark.asyncio
async def test_run_preflight_app_repo_entitlement_pass_on_200() -> None:
    async with _healthy_client() as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="app-repo-entitlement")
    assert row.status is PreflightStatus.PASS


@pytest.mark.asyncio
async def test_run_preflight_app_repo_entitlement_fail_on_403() -> None:
    async with _client(_handler(sys_app=_sn_error(403))) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="app-repo-entitlement")
    assert row.status is PreflightStatus.FAIL


@pytest.mark.asyncio
async def test_run_preflight_app_repo_entitlement_unknown_on_404() -> None:
    async with _client(_handler(sys_app=_sn_error(404))) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="app-repo-entitlement")
    assert row.status is PreflightStatus.UNKNOWN


@pytest.mark.asyncio
async def test_run_preflight_403_asymmetry_sn_cicd_unknown_app_repo_fail() -> None:
    # The asymmetry is the point (AC1 rows govern AC2's default): the SAME
    # 403 response maps to UNKNOWN on the sn_cicd-role item (unreadable
    # sys_user_role = the probe could not look) and to FAIL on the
    # app-repo item (a 403 on sys_app IS the entitlement signal).
    handler = _handler(sys_user_role=_sn_error(403), sys_app=_sn_error(403))
    async with _client(handler) as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    role_row = _find(report, instance="old", item="sn-cicd-role")
    repo_row = _find(report, instance="old", item="app-repo-entitlement")
    assert role_row.status is PreflightStatus.UNKNOWN
    assert repo_row.status is PreflightStatus.FAIL


# -- AC1: auth mode -- always reported, never FAIL ---------------------------


@pytest.mark.asyncio
async def test_run_preflight_auth_mode_pass_when_oauth() -> None:
    async with _healthy_client() as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="auth-mode")
    assert row.status is PreflightStatus.PASS
    assert row.detail == "oauth"


@pytest.mark.asyncio
async def test_run_preflight_auth_mode_pass_is_case_insensitive() -> None:
    async with _healthy_client() as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="OAuth", auth_mode_new="oauth")
    row = _find(report, instance="old", item="auth-mode")
    assert row.status is PreflightStatus.PASS


@pytest.mark.asyncio
async def test_run_preflight_auth_mode_unknown_when_basic() -> None:
    async with _healthy_client() as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="basic", auth_mode_new="oauth")
    row = _find(report, instance="old", item="auth-mode")
    assert row.status is PreflightStatus.UNKNOWN
    assert row.detail == "basic"


@pytest.mark.asyncio
async def test_run_preflight_auth_mode_unknown_when_unrecognized() -> None:
    async with _healthy_client() as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="", auth_mode_new="oauth")
    row = _find(report, instance="old", item="auth-mode")
    assert row.status is PreflightStatus.UNKNOWN


# -- AC4: both instances probed, grouped -------------------------------------


@pytest.mark.asyncio
async def test_run_preflight_covers_both_instances_for_every_item() -> None:
    async with _healthy_client() as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="basic")
    instances_by_item: dict[str, set[str]] = {}
    for row in report.items:
        instances_by_item.setdefault(row.item, set()).add(row.instance)
    assert instances_by_item == {
        "cicd-plugin": {"old", "new"},
        "sn-cicd-role": {"old", "new"},
        "app-repo-entitlement": {"old", "new"},
        "auth-mode": {"old", "new"},
    }
    assert len(report.items) == 8


# -- Deterministic ordering ---------------------------------------------------


@pytest.mark.asyncio
async def test_run_preflight_items_sorted_by_instance_then_item() -> None:
    async with _healthy_client() as old, _healthy_client() as new:
        report = await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    keys = [(row.instance, row.item) for row in report.items]
    assert keys == sorted(keys)


# -- AC5: GET-only, dedicated per instance ------------------------------------


@pytest.mark.asyncio
async def test_run_preflight_old_instance_issues_get_only() -> None:
    old_methods: list[str] = []
    async with _client(_handler(methods=old_methods)) as old, _healthy_client() as new:
        await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    assert old_methods
    assert set(old_methods) == {"GET"}


@pytest.mark.asyncio
async def test_run_preflight_new_instance_issues_get_only() -> None:
    new_methods: list[str] = []
    async with _healthy_client() as old, _client(_handler(methods=new_methods)) as new:
        await run_preflight(old, new, auth_mode_old="oauth", auth_mode_new="oauth")
    assert new_methods
    assert set(new_methods) == {"GET"}
