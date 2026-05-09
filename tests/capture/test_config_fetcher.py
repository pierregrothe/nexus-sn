# tests/capture/test_config_fetcher.py
# Tests for ConfigFetcher.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Tests for the ConfigFetcher component."""

import pytest

from nexus.capture.fetcher import ConfigFetcher
from nexus.capture.models import SnRecord
from nexus.capture.tables import DEFAULT_TABLE_GROUPS
from nexus.connectors.servicenow.errors import SNClientError
from tests.fakes.fake_sn_client import FakeServiceNowClient

_SCOPE_ID = "scope001"

_SKILL_S1: SnRecord = {
    "sys_id": "s1",
    "name": "Skill s1",
    "sys_scope": _SCOPE_ID,
    "sys_customer_update": "true",
}
_SKILL_S2: SnRecord = {
    "sys_id": "s2",
    "name": "Skill s2",
    "sys_scope": _SCOPE_ID,
    "sys_customer_update": "true",
}
_FLOW_F1: SnRecord = {
    "sys_id": "f1",
    "name": "Flow f1",
    "sys_scope": _SCOPE_ID,
    "sys_customer_update": "true",
}
_LOGIC_L1: SnRecord = {
    "sys_id": "l1",
    "flow": "f1",
    "sys_scope": _SCOPE_ID,
    "sys_customer_update": "true",
}
_LOGIC_L2: SnRecord = {
    "sys_id": "l2",
    "flow": "f1",
    "sys_scope": _SCOPE_ID,
    "sys_customer_update": "true",
}


class _CountRaisesClient(FakeServiceNowClient):
    """Fake that raises SNClientError on count_records for a specified table."""

    def __init__(self, raise_table: str, status_code: int) -> None:
        """Initialize with raise_table and status_code override."""
        super().__init__()
        self._raise_table = raise_table
        self._status_code = status_code

    async def count_records(self, table: str, query: str = "") -> int:
        """Raise SNClientError for the configured table, delegate otherwise."""
        if table == self._raise_table:
            raise SNClientError(f"HTTP {self._status_code}", status_code=self._status_code)
        return await super().count_records(table, query=query)


class _CountRaisesWithDataClient(_CountRaisesClient):
    """Variant with pre-seeded ai_skill data and count-raises on sys_hub_flow."""

    def __init__(self) -> None:
        """Seed ai_skill, raise 404 on sys_hub_flow count."""
        super().__init__(raise_table="sys_hub_flow", status_code=404)
        self._tables["ai_skill"] = [dict(r) for r in [_SKILL_S1]]


class _ListRaisesClient(FakeServiceNowClient):
    """Fake that raises SNClientError on list_records for a specified table."""

    def __init__(self, raise_table: str, status_code: int) -> None:
        """Initialize with raise_table and status_code override."""
        super().__init__()
        self._raise_table = raise_table
        self._status_code = status_code
        # Seed ai_skill and sys_hub_flow so count returns > 0 for the raise_table
        self._tables["ai_skill"] = [dict(r) for r in [_SKILL_S1]]
        self._tables["sys_hub_flow"] = [dict(r) for r in [_FLOW_F1]]

    async def list_records(
        self,
        table: str,
        query: str = "",
        limit: int = 1000,
        offset: int = 0,
        fields: str = "",
        display_value: str = "false",
    ) -> list[SnRecord]:
        """Raise SNClientError for the configured table, delegate otherwise."""
        if table == self._raise_table:
            raise SNClientError(f"HTTP {self._status_code}", status_code=self._status_code)
        return await super().list_records(
            table,
            query=query,
            limit=limit,
            offset=offset,
            fields=fields,
            display_value=display_value,
        )


@pytest.mark.asyncio
async def test_fetch_records_returns_config_records_for_scope() -> None:
    client = FakeServiceNowClient(
        initial_records={
            "ai_skill": [_SKILL_S1, _SKILL_S2],
        }
    )
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )

    skill_records = [r for r in records if r.table == "ai_skill"]
    assert len(skill_records) == 2
    assert {r.sys_id for r in skill_records} == {"s1", "s2"}


@pytest.mark.asyncio
async def test_fetch_records_includes_related_records() -> None:
    client = FakeServiceNowClient(
        initial_records={
            "sys_hub_flow": [_FLOW_F1],
            "sys_hub_flow_logic": [_LOGIC_L1, _LOGIC_L2],
        }
    )
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )

    logic_records = [r for r in records if r.table == "sys_hub_flow_logic"]
    assert len(logic_records) == 2
    assert all(r.parent_sys_id == "f1" for r in logic_records)


@pytest.mark.asyncio
async def test_fetch_records_unavailable_table_returns_empty_and_continues() -> None:
    # FakeServiceNowClient returns [] for unknown tables -- simulates unavailable
    client = FakeServiceNowClient(
        initial_records={
            "ai_skill": [_SKILL_S1],
            # sys_hub_flow not seeded -> returns [] (table absent = zero records)
        }
    )
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )

    tables_seen = {r.table for r in records}
    assert "ai_skill" in tables_seen
    assert "sys_hub_flow" not in tables_seen


@pytest.mark.asyncio
async def test_fetch_records_paginates_large_result_set() -> None:
    skills = [
        {"sys_id": str(i), "sys_scope": _SCOPE_ID, "sys_customer_update": "true"} for i in range(25)
    ]
    client = FakeServiceNowClient(initial_records={"ai_skill": skills})
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS, page_size=10)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )

    skill_records = [r for r in records if r.table == "ai_skill"]
    assert len(skill_records) == 25


@pytest.mark.asyncio
async def test_fetch_404_on_count_returns_empty_and_continues() -> None:
    client = _CountRaisesWithDataClient()
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )

    tables_seen = {r.table for r in records}
    assert "ai_skill" in tables_seen
    assert "sys_hub_flow" not in tables_seen


@pytest.mark.asyncio
async def test_fetch_500_on_count_propagates() -> None:
    client = _CountRaisesClient(raise_table="ai_skill", status_code=500)
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    with pytest.raises(SNClientError):
        async with client:
            await fetcher.fetch(
                instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
            )


@pytest.mark.asyncio
async def test_fetch_404_on_list_returns_empty_and_continues() -> None:
    client = _ListRaisesClient(raise_table="sys_hub_flow", status_code=404)
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )

    tables_seen = {r.table for r in records}
    assert "ai_skill" in tables_seen
    assert "sys_hub_flow" not in tables_seen


@pytest.mark.asyncio
async def test_fetch_500_on_list_propagates() -> None:
    client = _ListRaisesClient(raise_table="ai_skill", status_code=500)
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    with pytest.raises(SNClientError):
        async with client:
            await fetcher.fetch(
                instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
            )
