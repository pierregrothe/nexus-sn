# tests/test_plugins_scanner.py
# Tests for the async PluginScanner.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for PluginScanner.scan() against canned table data."""

import asyncio

import httpx
import pytest

from nexus.plugins.errors import PluginScanError
from nexus.plugins.models import PluginInventory
from nexus.plugins.scanner import (
    PluginScanner,
    _fetch_counts,
    _ScopeRecordCountError,
    _sum_scope_records,
)
from tests.fakes.fake_plugin_data import SYS_STORE_APP_ROWS, V_PLUGIN_ROWS

__all__: list[str] = []


def _transport_for(
    v_plugin_status: int = 200,
    store_status: int = 200,
    v_plugin_rows: list[dict[str, object]] | None = None,
    store_rows: list[dict[str, object]] | None = None,
    stats_status: int = 200,
    stats_payload: dict[str, object] | None = None,
) -> httpx.MockTransport:
    """Build a transport that serves all three endpoints with the given rows/status."""
    v_rows = v_plugin_rows if v_plugin_rows is not None else V_PLUGIN_ROWS
    s_rows = store_rows if store_rows is not None else SYS_STORE_APP_ROWS
    body: dict[str, object] = stats_payload if stats_payload is not None else {"result": []}

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(stats_status, json=body)
        if "v_plugin" in req.url.path:
            return httpx.Response(v_plugin_status, json={"result": v_rows})
        if "sys_store_app" in req.url.path:
            return httpx.Response(store_status, json={"result": s_rows})
        return httpx.Response(404, json={"result": []})

    return httpx.MockTransport(handler)


async def _scan(transport: httpx.MockTransport) -> PluginInventory:
    """Run a scan against the given mock transport."""
    scanner = PluginScanner(transport=transport)
    return await scanner.scan(url="https://dev.service-now.com", token="t", sn_version="Xanadu")


def test_scan_returns_inventory_with_captured_at_and_sn_version() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    assert inv.sn_version == "Xanadu"
    assert inv.captured_at is not None


def test_scan_dedupes_plugin_present_in_both_tables() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    incidents = [p for p in inv.plugins if p.plugin_id == "com.snc.incident"]
    assert len(incidents) == 1


def test_scan_marks_servicenow_vendor_as_servicenow_source() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.source == "servicenow"


def test_scan_marks_third_party_vendor_as_store_source() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    helper = next(p for p in inv.plugins if p.plugin_id == "com.acme.helper")
    assert helper.source == "store"


def test_scan_marks_x_scope_as_custom_source() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    custom = next(p for p in inv.plugins if p.plugin_id == "x_company_app")
    assert custom.source == "custom"


def test_scan_maps_active_true_to_state_active() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.state == "active"


def test_scan_maps_active_false_to_state_inactive() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    legacy = next(p for p in inv.plugins if p.plugin_id == "com.snc.legacy_only")
    assert legacy.state == "inactive"


def test_scan_resolves_curated_product_family_for_known_plugin() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.product_family == "ITSM"


def test_scan_resolves_uncategorized_for_unknown_plugin() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    helper = next(p for p in inv.plugins if p.plugin_id == "com.acme.helper")
    assert helper.product_family == "Uncategorized"


def test_scan_parses_comma_separated_dependencies() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    discovery = next(p for p in inv.plugins if p.plugin_id == "com.snc.discovery")
    assert discovery.depends_on == ("com.snc.cmdb",)


def test_scan_falls_back_to_store_when_v_plugin_unreadable() -> None:
    """403 on v_plugin should not abort; sys_store_app rows still return."""
    inv = asyncio.run(_scan(_transport_for(v_plugin_status=403)))
    ids = {p.plugin_id for p in inv.plugins}
    assert "com.acme.helper" in ids


def test_scan_falls_back_to_v_plugin_when_store_unreadable() -> None:
    inv = asyncio.run(_scan(_transport_for(store_status=403)))
    ids = {p.plugin_id for p in inv.plugins}
    assert "com.snc.discovery" in ids


def test_scan_raises_plugin_scan_error_when_both_tables_fail() -> None:
    with pytest.raises(PluginScanError):
        asyncio.run(_scan(_transport_for(v_plugin_status=500, store_status=500)))


def test_scan_resolves_scope_dict_form_to_plugin_id() -> None:
    """SN returns sys_store_app.scope as {value, display_value} when display_value=true."""
    dict_scope_rows: list[dict[str, object]] = [
        {
            "sys_id": "ref001",
            "scope": {"value": "com.snc.problem", "display_value": "Problem Management"},
            "name": "Problem Management",
            "version": "1.0",
            "active": "true",
            "vendor": "ServiceNow",
            "dependencies": "",
            "sys_created_on": "2024-05-01 08:00:00",
        }
    ]
    inv = asyncio.run(_scan(_transport_for(store_rows=dict_scope_rows, v_plugin_rows=[])))
    ids = {p.plugin_id for p in inv.plugins}
    assert "com.snc.problem" in ids


def test_scan_populates_latest_version_when_present() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    helper = next(p for p in inv.plugins if p.plugin_id == "com.acme.helper")
    assert helper.latest_version == "3.2.0"


def test_scan_leaves_latest_version_none_when_field_absent() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.latest_version is None


def test_scan_populates_vendor_from_store_row() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    acme = next(p for p in inv.plugins if p.plugin_id == "com.acme.helper")
    assert acme.vendor == "Acme Corp"


def test_scan_leaves_vendor_empty_for_v_plugin_only_record() -> None:
    inv = asyncio.run(_scan(_transport_for()))
    legacy = next(p for p in inv.plugins if p.plugin_id == "com.snc.legacy_only")
    assert legacy.vendor == ""


def _stats_response(rows: list[dict[str, object]]) -> dict[str, object]:
    return {"result": rows}


def _stats_row(table: str, count: int) -> dict[str, object]:
    return {
        "stats": {"count": str(count)},
        "groupby_fields": [{"field": "sys_class_name", "value": table}],
    }


async def _run_sum(transport: httpx.MockTransport, plugin_id: str = "com.x") -> int:
    async with httpx.AsyncClient(
        base_url="https://x.example",
        headers={"Authorization": "Bearer t"},
        transport=transport,
    ) as client:
        return await _sum_scope_records(client, plugin_id)


def test_sum_scope_records_returns_total_across_tables() -> None:
    transport = _transport_for(
        stats_payload=_stats_response(
            [
                _stats_row("sys_script", 100),
                _stats_row("sys_business_rule", 25),
            ]
        ),
    )
    total = asyncio.run(_run_sum(transport))
    assert total == 125


def test_sum_scope_records_returns_zero_for_empty_result() -> None:
    transport = _transport_for(stats_payload=_stats_response([]))
    total = asyncio.run(_run_sum(transport))
    assert total == 0


def test_sum_scope_records_raises_on_non_200() -> None:
    transport = _transport_for(stats_status=403)
    with pytest.raises(_ScopeRecordCountError):
        asyncio.run(_run_sum(transport))


def test_sum_scope_records_raises_on_malformed_response() -> None:
    transport = _transport_for(stats_payload={"no_result_key": True})
    with pytest.raises(_ScopeRecordCountError):
        asyncio.run(_run_sum(transport))


def test_fetch_counts_returns_count_per_plugin() -> None:
    transport = _transport_for(
        stats_payload=_stats_response([_stats_row("sys_script", 7)]),
    )

    async def _run() -> dict[str, int | None]:
        async with httpx.AsyncClient(
            base_url="https://x.example",
            headers={"Authorization": "Bearer t"},
            transport=transport,
        ) as client:
            return await _fetch_counts(client, ("com.a", "com.b"))

    counts = asyncio.run(_run())
    assert counts == {"com.a": 7, "com.b": 7}


def test_fetch_counts_marks_failed_plugin_as_none() -> None:
    transport = _transport_for(stats_status=500)

    async def _run() -> dict[str, int | None]:
        async with httpx.AsyncClient(
            base_url="https://x.example",
            headers={"Authorization": "Bearer t"},
            transport=transport,
        ) as client:
            return await _fetch_counts(client, ("com.a", "com.b"))

    counts = asyncio.run(_run())
    assert counts == {"com.a": None, "com.b": None}


def test_fetch_counts_caps_concurrent_calls_at_max_concurrency() -> None:
    in_flight = {"current": 0, "max": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        in_flight["current"] += 1
        if in_flight["current"] > in_flight["max"]:
            in_flight["max"] = in_flight["current"]
        try:
            return httpx.Response(200, json={"result": []})
        finally:
            in_flight["current"] -= 1

    transport = httpx.MockTransport(handler)

    async def _run() -> None:
        async with httpx.AsyncClient(
            base_url="https://x.example",
            headers={"Authorization": "Bearer t"},
            transport=transport,
        ) as client:
            ids = tuple(f"com.p{i}" for i in range(64))
            await _fetch_counts(client, ids, max_concurrency=4)

    asyncio.run(_run())
    assert in_flight["max"] <= 4


def test_scan_populates_record_count_from_aggregate_api() -> None:
    transport = _transport_for(
        stats_payload=_stats_response([_stats_row("sys_script", 42)]),
    )
    inv = asyncio.run(_scan(transport))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.record_count == 42


def test_scan_sets_record_count_none_when_aggregate_call_fails() -> None:
    transport = _transport_for(stats_status=500)
    inv = asyncio.run(_scan(transport))
    assert all(p.record_count is None for p in inv.plugins)


def test_scan_keeps_other_fields_intact_after_count_capture() -> None:
    transport = _transport_for(
        stats_payload=_stats_response([_stats_row("sys_script", 5)]),
    )
    inv = asyncio.run(_scan(transport))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.state == "active"
    assert incident.source == "servicenow"
    assert incident.version == "1.2.3"
