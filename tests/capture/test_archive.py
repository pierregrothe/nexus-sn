# tests/capture/test_archive.py
# Tests for ArchiveWriter and ArchiveReader.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Tests for the ArchiveWriter and ArchiveReader components."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.capture.archive import ArchiveReader, ArchiveWriter
from nexus.capture.errors import ArchiveCorruptError
from nexus.capture.models import CaptureResult, ConfigRecord, SnRefField

_NOW = datetime(2026, 5, 9, 14, 0, 0, tzinfo=UTC)


def _make_result() -> CaptureResult:
    ref: SnRefField = {"value": "global", "display_value": "Global"}
    r1 = ConfigRecord(
        sys_id="abc123",
        table="ai_skill",
        scope_sys_id="scope001",
        scope_name="x_app",
        captured_at=_NOW,
        fields={"name": "My Skill", "sys_scope": ref},
        parent_sys_id=None,
    )
    r2 = ConfigRecord(
        sys_id="def456",
        table="sys_hub_flow",
        scope_sys_id="scope001",
        scope_name="x_app",
        captured_at=_NOW,
        fields={"name": "My Flow"},
        parent_sys_id=None,
    )
    r3 = ConfigRecord(
        sys_id="ghi789",
        table="sys_hub_flow_logic",
        scope_sys_id="scope001",
        scope_name="x_app",
        captured_at=_NOW,
        fields={"name": "Step 1"},
        parent_sys_id="def456",
    )
    return CaptureResult(
        instance_id="dev-instance",
        captured_at=_NOW,
        scope_ids=("scope001",),
        table_group="ai_automation",
        records=(r1, r2, r3),
    )


def test_archive_writer_creates_manifest_yaml(tmp_path: Path) -> None:
    result = _make_result()
    writer = ArchiveWriter(archive_root=tmp_path)
    manifest = writer.write(result)

    assert manifest.record_count == 3
    assert manifest.instance_id == "dev-instance"
    assert (manifest.archive_dir / "manifest.yaml").exists()


def test_archive_writer_creates_per_record_yaml(tmp_path: Path) -> None:
    result = _make_result()
    writer = ArchiveWriter(archive_root=tmp_path)
    manifest = writer.write(result)

    archive = manifest.archive_dir
    assert (archive / "ai_skill" / "abc123.yaml").exists()
    assert (archive / "sys_hub_flow" / "def456.yaml").exists()


def test_archive_writer_nests_related_records_under_parent(tmp_path: Path) -> None:
    result = _make_result()
    writer = ArchiveWriter(archive_root=tmp_path)
    manifest = writer.write(result)

    nested = manifest.archive_dir / "sys_hub_flow" / "def456" / "sys_hub_flow_logic" / "ghi789.yaml"
    assert nested.exists()


def test_archive_reader_roundtrip_preserves_all_fields(tmp_path: Path) -> None:
    result = _make_result()
    writer = ArchiveWriter(archive_root=tmp_path)
    manifest = writer.write(result)

    reader = ArchiveReader()
    loaded = reader.read(manifest.archive_dir / "manifest.yaml")

    assert loaded.instance_id == result.instance_id
    assert len(loaded.records) == len(result.records)
    skill = next(r for r in loaded.records if r.table == "ai_skill")
    assert skill.sys_id == "abc123"
    assert skill.fields["name"] == "My Skill"
    assert skill.fields["sys_scope"] == {"value": "global", "display_value": "Global"}


def test_archive_reader_roundtrip_preserves_scalar_field_types(tmp_path: Path) -> None:
    ref: SnRefField = {"value": "global", "display_value": "Global"}
    record = ConfigRecord(
        sys_id="scalar1",
        table="ai_skill",
        scope_sys_id="scope001",
        scope_name="x_app",
        captured_at=_NOW,
        fields={
            "name": "Scalar Skill",
            "active": True,
            "disabled": False,
            "order": 100,
            "zero_order": 0,
            "weight": 2.5,
            "description": None,
            "sys_scope": ref,
        },
        parent_sys_id=None,
    )
    result = CaptureResult(
        instance_id="dev-instance",
        captured_at=_NOW,
        scope_ids=("scope001",),
        table_group="ai_automation",
        records=(record,),
    )
    writer = ArchiveWriter(archive_root=tmp_path)
    manifest = writer.write(result)

    reader = ArchiveReader()
    loaded = reader.read(manifest.archive_dir / "manifest.yaml")

    loaded_fields = loaded.records[0].fields
    assert loaded_fields["active"] is True
    assert type(loaded_fields["active"]) is bool
    assert loaded_fields["disabled"] is False
    assert type(loaded_fields["disabled"]) is bool
    assert loaded_fields["order"] == 100
    assert type(loaded_fields["order"]) is int
    assert loaded_fields["zero_order"] == 0
    assert type(loaded_fields["zero_order"]) is int
    assert loaded_fields["weight"] == 2.5
    assert type(loaded_fields["weight"]) is float
    assert loaded_fields["description"] is None
    assert loaded_fields["sys_scope"] == ref


def test_archive_reader_corrupt_manifest_raises(tmp_path: Path) -> None:
    bad_dir = tmp_path / "bad_archive"
    bad_dir.mkdir()
    with pytest.raises(ArchiveCorruptError):
        ArchiveReader().read(bad_dir / "manifest.yaml")
