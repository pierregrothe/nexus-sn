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
from nexus.schema.models import (
    FieldDef,
    InheritanceEdge,
    ReferenceEdge,
    RelationshipEdge,
    SchemaGraph,
    TableDef,
)


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


def test_write_then_read_roundtrips_graph_with_neighbors_and_edges(tmp_path: Path) -> None:
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, 12, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(
            TableDef(
                name="content_config",
                label="Content configuration",
                scope="sn_grc_doc_design",
                super_class="base_table",
                fields=(
                    FieldDef(name="sys_id", label="Sys ID", type="GUID", mandatory=True),
                    FieldDef(
                        name="data_relationship",
                        label="Data rel",
                        type="reference",
                        reference_target="data_relationship",
                    ),
                ),
            ),
            TableDef(name="base_table", label="Base", scope="sn_grc_doc_design"),
            TableDef(name="cmdb_ci", label="CI", scope="", is_neighbor=True),
        ),
        reference_edges=(
            ReferenceEdge(
                from_table="content_config",
                field="configuration_item",
                to_table="cmdb_ci",
                cross_scope=True,
            ),
        ),
        inheritance_edges=(
            InheritanceEdge(table="content_config", extends="base_table", cross_scope=False),
        ),
        relationship_edges=(
            RelationshipEdge(name="r", apply_to="content_config", query_from="base_table"),
        ),
    )
    path = SchemaArchiveWriter(tmp_path).write(graph)
    assert SchemaArchiveReader().read(path) == graph


def test_write_same_timestamp_overwrites_previous_snapshot(tmp_path: Path) -> None:
    # Pins current behavior: filenames have second resolution, so a second
    # write for the same instance/area/timestamp replaces the first snapshot.
    first = _graph()
    second = SchemaGraph(
        instance_id=first.instance_id,
        area_key=first.area_key,
        discovered_at=first.discovered_at,
        scope_keys=first.scope_keys,
        tables=(TableDef(name="t2", label="T2", scope="sn_grc_doc_design"),),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )
    writer = SchemaArchiveWriter(tmp_path)
    first_path = writer.write(first)
    second_path = writer.write(second)
    assert second_path == first_path
    assert SchemaArchiveReader().read(second_path) == second
