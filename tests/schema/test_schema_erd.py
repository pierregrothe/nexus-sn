# tests/schema/test_schema_erd.py
# Tests for the Mermaid ERD emitter.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Emitter renders edges with correct cardinality and a bridge section."""

from datetime import UTC, datetime

from nexus.schema.erd import MermaidErdEmitter
from nexus.schema.models import FieldDef, ReferenceEdge, SchemaGraph, TableDef


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(
            TableDef(
                name="content_config",
                label="Content configuration",
                scope="sn_grc_doc_design",
                fields=(FieldDef(name="data_relationship", label="Data rel", type="reference"),),
            ),
            TableDef(name="data_relationship", label="Data relationship", scope="sn_grc_doc_design"),
            TableDef(name="sn_data_registry_relationship", label="Registry", scope="", is_neighbor=True),
        ),
        reference_edges=(
            ReferenceEdge(from_table="content_config", field="data_relationship",
                          to_table="data_relationship", cross_scope=False),
            ReferenceEdge(from_table="data_relationship", field="data_registry",
                          to_table="sn_data_registry_relationship", cross_scope=True),
        ),
        inheritance_edges=(),
        relationship_edges=(),
    )


def test_render_contains_mermaid_erdiagram_block() -> None:
    out = MermaidErdEmitter().render(_graph())
    assert "```mermaid" in out
    assert "erDiagram" in out


def test_render_reference_edge_renders_many_to_one() -> None:
    out = MermaidErdEmitter().render(_graph())
    assert 'content_config }o--|| data_relationship : "data_relationship"' in out


def test_render_cross_scope_bridge_section_lists_cross_scope_edges() -> None:
    out = MermaidErdEmitter().render(_graph())
    assert "## Cross-scope bridges" in out
    assert "data_relationship.data_registry -> sn_data_registry_relationship" in out


def test_render_field_appendix_lists_table_fields() -> None:
    out = MermaidErdEmitter().render(_graph())
    assert "## Fields" in out
    assert "data_relationship" in out
