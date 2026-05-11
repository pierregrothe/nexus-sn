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
from nexus.plugins.scanner import PluginScanner
from tests.fakes.fake_plugin_data import SYS_STORE_APP_ROWS, V_PLUGIN_ROWS

__all__: list[str] = []


def _transport_for(
    v_plugin_status: int = 200,
    store_status: int = 200,
    v_plugin_rows: list[dict[str, object]] | None = None,
    store_rows: list[dict[str, object]] | None = None,
) -> httpx.MockTransport:
    """Build a transport that serves both tables with the given rows/status."""
    v_rows = v_plugin_rows if v_plugin_rows is not None else V_PLUGIN_ROWS
    s_rows = store_rows if store_rows is not None else SYS_STORE_APP_ROWS

    def handler(req: httpx.Request) -> httpx.Response:
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
