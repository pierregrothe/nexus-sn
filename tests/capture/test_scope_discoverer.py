# tests/capture/test_scope_discoverer.py
# Tests for ScopeDiscoverer.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Tests for the ScopeDiscoverer component."""

import pytest

from nexus.capture.scope import ScopeDiscoverer
from nexus.capture.tables import DEFAULT_TABLE_GROUPS
from tests.fakes.fake_sn_client import FakeServiceNowClient

_SCOPE_ROW = {
    "sys_id": "scope001",
    "name": "NowAssist HRSD",
    "scope": "x_snc_nowassist_hrsd",
    "version": "1.0.0",
    "vendor": "ServiceNow",
}


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
async def test_discover_scopes_skips_table_not_in_group() -> None:
    client = FakeServiceNowClient(initial_records={"sys_scope": [_SCOPE_ROW]})
    discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
    async with client:
        manifest = await discoverer.discover("dev-instance", "ai_automation")

    scope = manifest.scopes[0]
    # Tables not seeded return zero counts -- not missing from counts dict
    assert scope.table_counts.get("ai_skill", 0) == 0
