# tests/capture/test_update_set_writer.py
# Tests for UpdateSetWriter.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Tests for the UpdateSetWriter component."""

from datetime import UTC, datetime

import pytest

from nexus.capture.models import CaptureResult, ConfigRecord
from nexus.capture.update_set import UpdateSetWriter
from nexus.capture.xml_builder import UpdateSetXmlBuilder
from tests.fakes.fake_sn_client import FakeServiceNowClient

_NOW = datetime(2026, 5, 9, tzinfo=UTC)


def _result(records: list[ConfigRecord]) -> CaptureResult:
    return CaptureResult(
        instance_id="dev",
        captured_at=_NOW,
        scope_ids=("scope001",),
        table_group="ai_automation",
        records=tuple(records),
    )


def _record(sys_id: str) -> ConfigRecord:
    return ConfigRecord(
        sys_id=sys_id,
        table="ai_skill",
        scope_sys_id="scope001",
        scope_name="x_app",
        captured_at=_NOW,
        fields={"name": f"Skill {sys_id}"},
        parent_sys_id=None,
    )


@pytest.mark.asyncio
async def test_update_set_writer_creates_set_when_not_found() -> None:
    client = FakeServiceNowClient()
    writer = UpdateSetWriter(client, UpdateSetXmlBuilder())
    async with client:
        ref = await writer.push(_result([_record("r1")]), "dev", "NEXUS-test")

    assert ref.name == "NEXUS-test"
    assert ref.record_count == 1
    assert len(client._tables.get("sys_update_xml", [])) == 1


@pytest.mark.asyncio
async def test_update_set_writer_reuses_existing_in_progress_set() -> None:
    existing_set = {"sys_id": "existing001", "name": "NEXUS-test", "state": "in progress"}
    client = FakeServiceNowClient(initial_records={"sys_update_set": [existing_set]})
    writer = UpdateSetWriter(client, UpdateSetXmlBuilder())
    async with client:
        ref = await writer.push(_result([_record("r1")]), "dev", "NEXUS-test")

    assert ref.sys_id == "existing001"
    assert len(client._tables.get("sys_update_set", [])) == 1  # no new set created


@pytest.mark.asyncio
async def test_update_set_writer_sets_correct_record_count() -> None:
    client = FakeServiceNowClient()
    writer = UpdateSetWriter(client, UpdateSetXmlBuilder())
    async with client:
        ref = await writer.push(
            _result([_record("r1"), _record("r2"), _record("r3")]),
            "dev",
            "NEXUS-test",
        )

    assert ref.record_count == 3
