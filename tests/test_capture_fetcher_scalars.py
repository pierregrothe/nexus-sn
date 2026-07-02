# tests/test_capture_fetcher_scalars.py
# Tests for scalar field-value fidelity in ConfigFetcher._row_to_record (story 01a).
# Author: Pierre Grothe
# Date: 2026-07-02

"""AC1/AC2: bool/int/float/None field values survive capture with native types.

Before this story, ``_row_to_record`` kept only ``str`` and reference-dict
field values, silently dropping bool/int/float/None. These tests pin the
fixed behavior: every scalar kind survives into ``ConfigRecord.fields`` with
its exact native Python type (``True`` stays ``bool``, never coerces to
``1``), alongside plain strings and reference-dict fields.
"""

import pytest

from nexus.capture.fetcher import ConfigFetcher
from nexus.capture.models import SnRecord, SnRefField
from nexus.capture.tables import DEFAULT_TABLE_GROUPS
from tests.fakes.fake_sn_client import FakeServiceNowClient

_SCOPE_ID = "scope001"

_SKILL_ALL_SCALARS: SnRecord = {
    "sys_id": "s1",
    "name": "Scalar Skill",
    "sys_scope": _SCOPE_ID,
    "sys_customer_update": "true",
    "active": True,
    "disabled": False,
    "order": 100,
    "zero_order": 0,
    "weight": 2.5,
    "description": None,
}


async def _fetch_skill(row: SnRecord) -> SnRecord:
    client = FakeServiceNowClient(initial_records={"ai_skill": [row]})
    fetcher = ConfigFetcher(client, DEFAULT_TABLE_GROUPS)
    async with client:
        records = await fetcher.fetch(
            instance_id="dev", scope_ids=[_SCOPE_ID], table_group="ai_automation"
        )
    return next(r for r in records if r.table == "ai_skill").fields


@pytest.mark.asyncio
async def test_row_to_record_preserves_true_bool_field_native_type() -> None:
    fields = await _fetch_skill(_SKILL_ALL_SCALARS)
    assert fields["active"] is True
    assert type(fields["active"]) is bool


@pytest.mark.asyncio
async def test_row_to_record_preserves_false_bool_field_without_dropping() -> None:
    fields = await _fetch_skill(_SKILL_ALL_SCALARS)
    assert "disabled" in fields
    assert fields["disabled"] is False
    assert type(fields["disabled"]) is bool


@pytest.mark.asyncio
async def test_row_to_record_preserves_int_field_native_type() -> None:
    fields = await _fetch_skill(_SKILL_ALL_SCALARS)
    assert fields["order"] == 100
    assert type(fields["order"]) is int


@pytest.mark.asyncio
async def test_row_to_record_preserves_zero_int_field_without_dropping() -> None:
    fields = await _fetch_skill(_SKILL_ALL_SCALARS)
    assert "zero_order" in fields
    assert fields["zero_order"] == 0
    assert type(fields["zero_order"]) is int


@pytest.mark.asyncio
async def test_row_to_record_preserves_float_field_native_type() -> None:
    fields = await _fetch_skill(_SKILL_ALL_SCALARS)
    assert fields["weight"] == 2.5
    assert type(fields["weight"]) is float


@pytest.mark.asyncio
async def test_row_to_record_preserves_none_field_without_dropping() -> None:
    fields = await _fetch_skill(_SKILL_ALL_SCALARS)
    assert "description" in fields
    assert fields["description"] is None


@pytest.mark.asyncio
async def test_row_to_record_combines_scalars_str_and_ref_without_dropping_any() -> None:
    ref_value: SnRefField = {"value": "scope001", "display_value": "NowAssist HRSD"}
    row: SnRecord = {**_SKILL_ALL_SCALARS, "sys_scope": ref_value}
    fields = await _fetch_skill(row)
    assert fields["name"] == "Scalar Skill"
    assert fields["sys_scope"] == ref_value
    assert fields["active"] is True
    assert fields["disabled"] is False
    assert fields["order"] == 100
    assert fields["zero_order"] == 0
    assert fields["weight"] == 2.5
    assert fields["description"] is None
