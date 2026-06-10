# tests/fakes/test_fake_sn_client.py
# Tests for FakeServiceNowClient list_records encoded-query interpretation.
# Author: Pierre Grothe
# Date: 2026-06-09

"""Verify the FakeServiceNowClient minimal encoded-query grammar."""

import pytest

from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__: list[str] = []

_ROWS: list[dict[str, object]] = [
    {"sys_id": "a", "state": "open", "hint": "first"},
    {"sys_id": "b", "state": "closed", "hint": ""},
    {"sys_id": "c", "state": "open", "hint": "third"},
]


def _client() -> FakeServiceNowClient:
    return FakeServiceNowClient(initial_records={"task": [dict(r) for r in _ROWS]})


@pytest.mark.asyncio
async def test_list_records_empty_query_returns_all() -> None:
    rows = await _client().list_records("task")
    assert {r["sys_id"] for r in rows} == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_list_records_in_operator_filters_by_membership() -> None:
    rows = await _client().list_records("task", query="sys_idINa,c")
    assert {r["sys_id"] for r in rows} == {"a", "c"}


@pytest.mark.asyncio
async def test_list_records_equals_operator_filters_by_value() -> None:
    rows = await _client().list_records("task", query="state=open")
    assert {r["sys_id"] for r in rows} == {"a", "c"}


@pytest.mark.asyncio
async def test_list_records_isnotempty_operator_filters_blank_values() -> None:
    rows = await _client().list_records("task", query="hintISNOTEMPTY")
    assert {r["sys_id"] for r in rows} == {"a", "c"}


@pytest.mark.asyncio
async def test_list_records_and_conjunction_requires_all_conditions() -> None:
    rows = await _client().list_records("task", query="state=open^hintISNOTEMPTY^sys_idINa,b")
    assert {r["sys_id"] for r in rows} == {"a"}


@pytest.mark.asyncio
async def test_list_records_or_alternatives_match_any_and_chain() -> None:
    rows = await _client().list_records("task", query="state=open^hint=first^ORsys_idINb")
    assert {r["sys_id"] for r in rows} == {"a", "b"}


@pytest.mark.asyncio
async def test_list_records_unknown_fragment_matches_all() -> None:
    rows = await _client().list_records("task", query="stateLIKEopen")
    assert {r["sys_id"] for r in rows} == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_list_records_unknown_fragment_in_conjunction_is_neutral() -> None:
    rows = await _client().list_records("task", query="state=open^numberLIKEinc")
    assert {r["sys_id"] for r in rows} == {"a", "c"}


@pytest.mark.asyncio
async def test_list_records_reference_dict_field_compares_value_key() -> None:
    seed = {"task": [{"sys_id": "r1", "sys_scope": {"link": "x/SCID", "value": "SCID"}}]}
    client = FakeServiceNowClient(initial_records=seed)
    rows = await client.list_records("task", query="sys_scopeINSCID,OTHER")
    assert [r["sys_id"] for r in rows] == ["r1"]


@pytest.mark.asyncio
async def test_list_records_applies_offset_and_limit_after_filtering() -> None:
    seed = {
        "task": [
            {"sys_id": "m1", "state": "open"},
            {"sys_id": "x1", "state": "closed"},
            {"sys_id": "m2", "state": "open"},
            {"sys_id": "m3", "state": "open"},
            {"sys_id": "m4", "state": "open"},
        ]
    }
    client = FakeServiceNowClient(initial_records=seed)
    rows = await client.list_records("task", query="state=open", limit=2, offset=2)
    assert [r["sys_id"] for r in rows] == ["m3", "m4"]


@pytest.mark.asyncio
async def test_list_records_records_calls_with_table_and_query() -> None:
    client = _client()
    await client.list_records("task", query="state=open")
    assert client.calls == [("task", "state=open")]
