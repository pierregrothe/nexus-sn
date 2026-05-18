# tests/test_instance_role_probe.py
# Unit tests for the OAuth-user role probe (Table API access checks).
# Author: Pierre Grothe
# Date: 2026-05-16
"""Tests for `nexus.instances.role_probe.probe_table_access`.

Covers the three status codes the CLI's diagnose-roles command will
actually translate into different rows: 200 (green), 403 (denied with
SN detail body), and 404 (table missing -- typically when the
relevant SN plugin is not installed on this instance).
"""

from __future__ import annotations

import httpx
import pytest

from nexus.instances.role_probe import (
    DEFAULT_PROBE_TABLES,
    TableProbe,
    probe_all,
    probe_table_access,
)

__all__: list[str] = []


def _client(transport: httpx.MockTransport) -> httpx.AsyncClient:
    """Build an httpx client wired to ``transport`` with a bearer header."""
    return httpx.AsyncClient(
        base_url="https://test.service-now.com",
        headers={"Authorization": "Bearer t", "Accept": "application/json"},
        transport=transport,
    )


@pytest.mark.asyncio
async def test_probe_table_access_returns_ok_for_200_response() -> None:
    """A 200 from SN flips ``ok`` true and leaves message/detail empty."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/now/table/sys_user"
        assert request.url.params["sysparm_limit"] == "1"
        return httpx.Response(200, json={"result": [{"sys_id": "u1"}]})

    probe = TableProbe(table="sys_user", purpose="Baseline identity", suggested_role="")
    async with _client(httpx.MockTransport(handler)) as client:
        result = await probe_table_access(client, probe)
    assert result.ok
    assert result.status_code == 200
    assert result.message == ""
    assert result.detail == ""


@pytest.mark.asyncio
async def test_probe_table_access_captures_sn_error_body_on_403() -> None:
    """403 with a ServiceNow error body surfaces message + detail."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={
                "error": {
                    "message": "User Not Authorized",
                    "detail": "ACL restricts access to sys_store_app; requires "
                    "app_store_pa_user_role.",
                },
                "status": "failure",
            },
        )

    probe = TableProbe(
        table="sys_store_app",
        purpose="Store-app catalog",
        suggested_role="app_store_pa_user_role",
    )
    async with _client(httpx.MockTransport(handler)) as client:
        result = await probe_table_access(client, probe)
    assert not result.ok
    assert result.status_code == 403
    assert result.message == "User Not Authorized"
    assert "app_store_pa_user_role" in result.detail


@pytest.mark.asyncio
async def test_probe_table_access_handles_404_table_missing() -> None:
    """A 404 means the table does not exist on this instance (plugin not installed)."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "Not Found", "detail": ""}})

    probe = TableProbe(table="sys_nonexistent_table", purpose="Hypothetical", suggested_role="")
    async with _client(httpx.MockTransport(handler)) as client:
        result = await probe_table_access(client, probe)
    assert not result.ok
    assert result.status_code == 404
    assert result.message == "Not Found"


@pytest.mark.asyncio
async def test_probe_table_access_handles_403_without_json_body() -> None:
    """A 403 with no JSON body leaves message/detail empty rather than crashing."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="Forbidden")

    probe = TableProbe(table="sys_metadata", purpose="Records", suggested_role="admin")
    async with _client(httpx.MockTransport(handler)) as client:
        result = await probe_table_access(client, probe)
    assert not result.ok
    assert result.status_code == 403
    assert result.message == ""
    assert result.detail == ""


@pytest.mark.asyncio
async def test_probe_all_returns_one_result_per_probe_in_order() -> None:
    """`probe_all` preserves order and runs each probe in the curated list."""
    seen_tables: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        seen_tables.append(path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"result": []})

    async with _client(httpx.MockTransport(handler)) as client:
        results = await probe_all(client)

    assert len(results) == len(DEFAULT_PROBE_TABLES)
    assert [r.probe.table for r in results] == [p.table for p in DEFAULT_PROBE_TABLES]
    assert seen_tables == [p.table for p in DEFAULT_PROBE_TABLES]
    assert all(r.ok for r in results)


@pytest.mark.asyncio
async def test_probe_table_access_reports_network_failure_as_zero_status() -> None:
    """Transport errors come back as status 0 with the exception class in message."""

    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    probe = TableProbe(table="sys_user", purpose="Baseline identity", suggested_role="")
    async with _client(httpx.MockTransport(handler)) as client:
        result = await probe_table_access(client, probe)
    assert not result.ok
    assert result.status_code == 0
    assert result.message == "ConnectError"
    assert "network down" in result.detail
