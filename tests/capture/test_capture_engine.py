# tests/capture/test_capture_engine.py
# Integration tests for CaptureEngine using all fakes.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Integration tests for CaptureEngine using FakeServiceNowClient."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.capture.engine import CaptureEngine
from nexus.capture.models import CaptureResult, ConfigRecord
from tests.fakes.fake_sn_client import FakeServiceNowClient

_SCOPE_ROW = {
    "sys_id": "scope001",
    "name": "NowAssist HRSD",
    "scope": "x_snc_nowassist_hrsd",
    "version": "1.0.0",
    "vendor": "SN",
}

_SKILL = {
    "sys_id": "skill001",
    "name": "My Skill",
    "sys_scope": "scope001",
    "sys_customer_update": "true",
}

_NOW = datetime(2026, 5, 9, tzinfo=UTC)


def _make_result(
    tmp_path: Path,
) -> tuple[CaptureEngine, CaptureResult, FakeServiceNowClient]:
    record = ConfigRecord(
        sys_id="r1",
        table="ai_skill",
        scope_sys_id="s1",
        scope_name="x_app",
        captured_at=_NOW,
        fields={"name": "Skill"},
        parent_sys_id=None,
    )
    result = CaptureResult(
        instance_id="dev",
        captured_at=_NOW,
        scope_ids=("s1",),
        table_group="ai_automation",
        records=(record,),
    )
    client = FakeServiceNowClient()
    engine = CaptureEngine(client=client, archive_root=tmp_path)
    return engine, result, client


@pytest.mark.asyncio
async def test_capture_engine_discover_returns_scope_manifest(tmp_path: Path) -> None:
    client = FakeServiceNowClient(initial_records={"sys_scope": [_SCOPE_ROW], "ai_skill": [_SKILL]})
    engine = CaptureEngine(client=client, archive_root=tmp_path)
    async with client:
        manifest = await engine.discover_scopes("dev", "ai_automation")

    assert len(manifest.scopes) == 1
    assert manifest.scopes[0].scope == "x_snc_nowassist_hrsd"


@pytest.mark.asyncio
async def test_capture_engine_capture_returns_result(tmp_path: Path) -> None:
    client = FakeServiceNowClient(initial_records={"sys_scope": [_SCOPE_ROW], "ai_skill": [_SKILL]})
    engine = CaptureEngine(client=client, archive_root=tmp_path)
    async with client:
        result = await engine.capture("dev", ["scope001"], "ai_automation")

    skill_records = [r for r in result.records if r.table == "ai_skill"]
    assert len(skill_records) == 1
    assert skill_records[0].sys_id == "skill001"


def test_capture_engine_save_and_load_roundtrip(tmp_path: Path) -> None:
    engine, result, _client = _make_result(tmp_path)

    manifest = engine.save_archive(result)
    loaded = engine.load_archive(manifest.archive_dir / "manifest.yaml")

    assert len(loaded.records) == 1
    assert loaded.records[0].sys_id == "r1"


@pytest.mark.asyncio
async def test_capture_engine_push_to_update_set_returns_ref(tmp_path: Path) -> None:
    engine, result, client = _make_result(tmp_path)
    async with client:
        ref = await engine.push_to_update_set(result, "dev", "NEXUS-test")

    assert ref.name == "NEXUS-test"
    assert ref.record_count == 1
    assert ref.instance_id == "dev"
    assert ref.state == "in progress"
