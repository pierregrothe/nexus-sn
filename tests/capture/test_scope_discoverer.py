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

# Scope metadata used as the sys_scope lookup response
_SCOPE_ROW = {
    "sys_id": "scope001",
    "name": "NowAssist HRSD",
    "scope": "x_snc_nowassist_hrsd",
    "version": "1.0.0",
    "vendor": "ServiceNow",
}


class _GroupedCountRaisesClient(FakeServiceNowClient):
    """Raises SNClientError on count_grouped for a specific table."""

    def __init__(self, raise_table: str, status_code: int) -> None:
        """Initialize with the table to fail and seeded scope + data."""
        super().__init__(
            initial_records={
                "sys_scope": [_SCOPE_ROW],
                # ai_skill seeded so the scope survives even if another table raises
                "ai_skill": [{"sys_id": "s1", "sys_scope": "scope001"}],
            }
        )
        self._raise_table = raise_table
        self._status_code = status_code

    async def count_grouped(self, table: str, *, query: str = "", group_by: str) -> dict[str, int]:
        """Raise SNClientError for the configured table, delegate otherwise."""
        if table == self._raise_table:
            raise SNClientError(f"HTTP {self._status_code}", status_code=self._status_code)
        return await super().count_grouped(table, query=query, group_by=group_by)


@pytest.mark.asyncio
async def test_discover_scopes_returns_manifest_with_counts() -> None:
    client = FakeServiceNowClient(
        initial_records={
            "sys_scope": [_SCOPE_ROW],
            "ai_skill": [
                {"sys_id": "s1", "sys_scope": "scope001"},
                {"sys_id": "s2", "sys_scope": "scope001"},
            ],
            "sys_hub_flow": [
                {"sys_id": "f1", "sys_scope": "scope001"},
            ],
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
async def test_discover_scopes_with_no_custom_records_returns_empty() -> None:
    # No table data seeded -> count_grouped returns {} for all tables -> no scopes
    client = FakeServiceNowClient(initial_records={"sys_scope": [_SCOPE_ROW]})
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    assert manifest.instance_id == "dev-instance"
    assert len(manifest.scopes) == 0


@pytest.mark.asyncio
async def test_discover_scopes_excludes_ootb_scopes_with_no_custom_records() -> None:
    # Scope exists in sys_scope but has no custom AI/automation records
    client = FakeServiceNowClient(initial_records={"sys_scope": [_SCOPE_ROW]})
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    assert len(manifest.scopes) == 0


@pytest.mark.asyncio
async def test_discover_scopes_unavailable_table_count_zero_scope_still_included() -> None:
    # sys_hub_flow raises 400 but ai_skill has records -> scope still appears
    client = _GroupedCountRaisesClient(raise_table="sys_hub_flow", status_code=400)
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    assert len(manifest.scopes) == 1
    scope = manifest.scopes[0]
    assert scope.table_counts["ai_skill"] == 1  # seeded in fake
    assert scope.table_counts["sys_hub_flow"] == 0  # 400 -> _safe_grouped_count returns {}
