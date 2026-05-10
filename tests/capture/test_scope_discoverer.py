# tests/capture/test_scope_discoverer.py
# Tests for ScopeDiscoverer.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Tests for the ScopeDiscoverer component."""

import pytest

from nexus.capture.scope import ScopeDiscoverer
from nexus.capture.tables import DEFAULT_TABLE_GROUPS
from nexus.connectors.servicenow.errors import SNClientError
from tests.fakes.fake_sn_client import FakeServiceNowClient

_SCOPE_ROW = {
    "sys_id": "scope001",
    "name": "NowAssist HRSD",
    "scope": "x_snc_nowassist_hrsd",
    "version": "1.0.0",
    "vendor": "ServiceNow",
}


class _CountRaisesClient(FakeServiceNowClient):
    """Raises SNClientError for count_records on a specific table, delegates otherwise."""

    def __init__(self, raise_table: str, status_code: int) -> None:
        """Initialize with one table that raises and ai_skill seeded with data."""
        super().__init__(
            initial_records={
                "sys_scope": [_SCOPE_ROW],
                # Seed ai_skill so the scope has at least one non-zero count
                # even when another table raises 400 -- scope stays in results.
                "ai_skill": [{"sys_id": "s1"}],
            }
        )
        self._raise_table = raise_table
        self._status_code = status_code

    async def count_records(self, table: str, query: str = "") -> int:
        """Raise SNClientError for the configured table, delegate otherwise."""
        if table == self._raise_table:
            raise SNClientError(f"HTTP {self._status_code}", status_code=self._status_code)
        return await super().count_records(table, query=query)


@pytest.mark.asyncio
async def test_discover_scopes_returns_manifest_with_counts() -> None:
    client = FakeServiceNowClient(
        initial_records={
            "sys_scope": [_SCOPE_ROW],
            "ai_skill": [{"sys_id": "s1"}, {"sys_id": "s2"}],
            "sys_hub_flow": [{"sys_id": "f1"}],
        }
    )
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    assert manifest.instance_id == "dev-instance"
    assert len(manifest.scopes) == 1
    scope = manifest.scopes[0]
    assert scope.sys_id == "scope001"
    assert scope.scope == "x_snc_nowassist_hrsd"
    assert scope.table_counts["ai_skill"] == 2
    assert scope.table_counts["sys_hub_flow"] == 1


@pytest.mark.asyncio
async def test_discover_scopes_with_empty_instance_returns_empty_manifest() -> None:
    client = FakeServiceNowClient(initial_records={"sys_scope": []})
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    assert manifest.instance_id == "dev-instance"
    assert len(manifest.scopes) == 0


@pytest.mark.asyncio
async def test_discover_scopes_excludes_ootb_scopes_with_no_custom_records() -> None:
    # Scope exists but has no custom records in any table -> excluded from manifest
    client = FakeServiceNowClient(initial_records={"sys_scope": [_SCOPE_ROW]})
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    assert len(manifest.scopes) == 0


@pytest.mark.asyncio
async def test_discover_scopes_unavailable_table_returns_zero_and_scope_included() -> None:
    # ai_skill returns 400 (table absent) but ai_skill is seeded so count=1 from
    # the non-raising path. sys_hub_flow raises -> count=0. Scope is included
    # because at least one table has a non-zero count.
    client = _CountRaisesClient(raise_table="sys_hub_flow", status_code=400)
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    assert len(manifest.scopes) == 1
    scope = manifest.scopes[0]
    assert scope.table_counts["ai_skill"] == 1  # seeded, count works
    assert scope.table_counts["sys_hub_flow"] == 0  # 400 -> _safe_count returns 0
