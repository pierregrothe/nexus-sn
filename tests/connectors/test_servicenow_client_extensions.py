# tests/connectors/test_servicenow_client_extensions.py
# Tests for list_records and count_records on ServiceNowClient.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Tests for the paginated list_records and count_records extensions."""

import pytest

from tests.fakes.fake_sn_client import FakeServiceNowClient


@pytest.mark.asyncio
async def test_list_records_returns_all_records_without_cap() -> None:
    records = [{"sys_id": str(i), "name": f"Record {i}"} for i in range(150)]
    client = FakeServiceNowClient(initial_records={"ai_skill": records})
    async with client:
        result = await client.list_records("ai_skill", limit=150, offset=0)
    assert len(result) == 150


@pytest.mark.asyncio
async def test_list_records_respects_offset() -> None:
    records = [{"sys_id": str(i)} for i in range(10)]
    client = FakeServiceNowClient(initial_records={"ai_skill": records})
    async with client:
        page1 = await client.list_records("ai_skill", limit=5, offset=0)
        page2 = await client.list_records("ai_skill", limit=5, offset=5)
    assert [r["sys_id"] for r in page1] == [str(i) for i in range(5)]
    assert [r["sys_id"] for r in page2] == [str(i) for i in range(5, 10)]


@pytest.mark.asyncio
async def test_count_records_returns_total() -> None:
    records = [{"sys_id": str(i)} for i in range(7)]
    client = FakeServiceNowClient(initial_records={"ai_skill": records})
    async with client:
        count = await client.count_records("ai_skill")
    assert count == 7


@pytest.mark.asyncio
async def test_count_records_on_empty_table_returns_zero() -> None:
    client = FakeServiceNowClient()
    async with client:
        count = await client.count_records("ai_skill")
    assert count == 0
