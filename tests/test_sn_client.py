# tests/test_sn_client.py
# Tests for the FakeServiceNowClient fake (validates the fake itself).
# Author: Pierre Grothe
# Date: 2026-05-07

"""Tests for FakeServiceNowClient."""

import pytest

from tests.fakes import FakeServiceNowClient


@pytest.mark.asyncio
async def test_fake_sn_create_record_assigns_sys_id() -> None:
    async with FakeServiceNowClient() as client:
        record = await client.create_record("incident", {"short_description": "Test"})
    assert "sys_id" in record
    assert record["short_description"] == "Test"


@pytest.mark.asyncio
async def test_fake_sn_query_table_returns_created_records() -> None:
    async with FakeServiceNowClient() as client:
        await client.create_record("incident", {"priority": "1"})
        await client.create_record("incident", {"priority": "2"})
        records = await client.query_table("incident")
    assert len(records) == 2


@pytest.mark.asyncio
async def test_fake_sn_query_table_respects_limit() -> None:
    initial = {"incident": [{"sys_id": str(i)} for i in range(10)]}
    async with FakeServiceNowClient(initial_records=initial) as client:
        records = await client.query_table("incident", limit=3)
    assert len(records) == 3


@pytest.mark.asyncio
async def test_fake_sn_query_table_returns_empty_for_unknown_table() -> None:
    async with FakeServiceNowClient() as client:
        records = await client.query_table("nonexistent_table")
    assert records == []


@pytest.mark.asyncio
async def test_fake_sn_get_record_returns_correct_record() -> None:
    async with FakeServiceNowClient() as client:
        created = await client.create_record("incident", {"priority": "1"})
        fetched = await client.get_record("incident", created["sys_id"])
    assert fetched["sys_id"] == created["sys_id"]


@pytest.mark.asyncio
async def test_fake_sn_get_record_returns_empty_for_missing_sys_id() -> None:
    async with FakeServiceNowClient() as client:
        result = await client.get_record("incident", "nonexistent-sys-id")
    assert result == {}


@pytest.mark.asyncio
async def test_fake_sn_update_record_modifies_field() -> None:
    async with FakeServiceNowClient() as client:
        created = await client.create_record("incident", {"state": "1"})
        updated = await client.update_record("incident", created["sys_id"], {"state": "6"})
    assert updated["state"] == "6"


@pytest.mark.asyncio
async def test_fake_sn_delete_record_removes_from_store() -> None:
    async with FakeServiceNowClient() as client:
        created = await client.create_record("incident", {"priority": "1"})
        await client.delete_record("incident", created["sys_id"])
        records = await client.query_table("incident")
    assert all(r.get("sys_id") != created["sys_id"] for r in records)
