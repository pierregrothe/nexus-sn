# tests/schema/test_schema_archive.py
# Tests for the schema JSON archive round-trip.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Writer + reader preserve the SchemaGraph; bad input raises."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from nexus.schema.archive import SchemaArchiveReader, SchemaArchiveWriter
from nexus.schema.errors import SchemaArchiveError
from nexus.schema.models import SchemaGraph, TableDef


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, 12, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(TableDef(name="t", label="T", scope="sn_grc_doc_design"),),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )


def test_write_then_read_roundtrips_graph(tmp_path: Path) -> None:
    path = SchemaArchiveWriter(tmp_path).write(_graph())
    loaded = SchemaArchiveReader().read(path)
    assert loaded == _graph()


def test_write_places_file_under_instance_dir(tmp_path: Path) -> None:
    path = SchemaArchiveWriter(tmp_path).write(_graph())
    assert path.parent == tmp_path / "alectri"
    assert path.suffix == ".json"


def test_read_missing_file_raises_archive_error(tmp_path: Path) -> None:
    with pytest.raises(SchemaArchiveError):
        SchemaArchiveReader().read(tmp_path / "nope.json")


def test_read_invalid_json_raises_archive_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(SchemaArchiveError):
        SchemaArchiveReader().read(bad)
