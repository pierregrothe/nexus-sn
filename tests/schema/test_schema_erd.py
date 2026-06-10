# tests/schema/test_schema_erd.py
# Tests for the Mermaid ERD emitter.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Emitter renders edges with correct cardinality and a bridge section."""

import re
from datetime import UTC, datetime

from nexus.schema.erd import MermaidErdEmitter, _token
from nexus.schema.models import (
    FieldDef,
    InheritanceEdge,
    ReferenceEdge,
    SchemaGraph,
    TableDef,
)

# Grammar for every line diagram() may emit. A future cardinality (e.g.
# '}o--o{') is a one-line addition here.
_ER_LINE_GRAMMAR: tuple[re.Pattern[str], ...] = (
    re.compile(r"erDiagram"),  # header
    re.compile(r"    \w+ \{"),  # entity open
    re.compile(r"        \w+ \w+( PK| FK)?"),  # attribute
    re.compile(r"    \}"),  # entity close
    re.compile(r'    \w+ \}o--\|\| \w+ : "[^"]+"'),  # reference edge
    re.compile(r'    \w+ \|\|--\|\| \w+ : "extends"'),  # inheritance edge
)


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
                fields=(
                    FieldDef(name="sys_id", label="Sys ID", type="GUID"),
                    FieldDef(name="name", label="Name", type="string"),
                    FieldDef(name="sys_created_by", label="Created by", type="string"),
                    FieldDef(
                        name="data_relationship",
                        label="Data rel",
                        type="reference",
                        reference_target="data_relationship",
                    ),
                ),
            ),
            TableDef(
                name="data_relationship", label="Data relationship", scope="sn_grc_doc_design"
            ),
            TableDef(
                name="sn_data_registry_relationship", label="Registry", scope="", is_neighbor=True
            ),
        ),
        reference_edges=(
            ReferenceEdge(
                from_table="content_config",
                field="data_relationship",
                to_table="data_relationship",
                cross_scope=False,
            ),
            ReferenceEdge(
                from_table="data_relationship",
                field="data_registry",
                to_table="sn_data_registry_relationship",
                cross_scope=True,
            ),
        ),
        inheritance_edges=(),
        relationship_edges=(),
    )


def _multi_entity_graph() -> SchemaGraph:
    """Two in-scope tables with fields, one reference edge, one inheritance edge."""
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
                fields=(
                    FieldDef(name="sys_id", label="Sys ID", type="GUID"),
                    FieldDef(
                        name="data_relationship",
                        label="Data rel",
                        type="reference",
                        reference_target="data_relationship",
                    ),
                ),
            ),
            TableDef(
                name="data_relationship",
                label="Data relationship",
                scope="sn_grc_doc_design",
                fields=(
                    FieldDef(name="sys_id", label="Sys ID", type="GUID"),
                    FieldDef(name="name", label="Name", type="string"),
                ),
            ),
        ),
        reference_edges=(
            ReferenceEdge(
                from_table="content_config",
                field="data_relationship",
                to_table="data_relationship",
                cross_scope=False,
            ),
        ),
        inheritance_edges=(
            InheritanceEdge(extends="data_relationship", table="content_config", cross_scope=False),
        ),
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
    assert "| data_relationship | reference | data_relationship |" in out


def test_render_inheritance_edge_renders_one_to_one() -> None:
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(
            TableDef(
                name="content_config", label="Content configuration", scope="sn_grc_doc_design"
            ),
            TableDef(name="base_table", label="Base", scope="sn_grc_doc_design"),
        ),
        reference_edges=(),
        inheritance_edges=(
            InheritanceEdge(extends="base_table", table="content_config", cross_scope=False),
        ),
        relationship_edges=(),
    )
    out = MermaidErdEmitter().render(graph)
    assert 'base_table ||--|| content_config : "extends"' in out


def test_render_cross_scope_bridge_section_shows_none_when_empty() -> None:
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(
            TableDef(
                name="content_config", label="Content configuration", scope="sn_grc_doc_design"
            ),
        ),
        reference_edges=(
            ReferenceEdge(
                from_table="content_config",
                field="data_rel",
                to_table="content_config",
                cross_scope=False,
            ),
        ),
        inheritance_edges=(),
        relationship_edges=(),
    )
    out = MermaidErdEmitter().render(graph)
    assert "- (none)" in out


def test_diagram_returns_bare_mermaid_source() -> None:
    diagram = MermaidErdEmitter().diagram(_graph())
    assert diagram.startswith("erDiagram")
    assert "}o--||" in diagram
    assert "```" not in diagram
    assert "# Schema ERD" not in diagram


def test_diagram_renders_entity_block_with_key_fields() -> None:
    diagram = MermaidErdEmitter().diagram(_graph())
    assert "content_config {" in diagram
    assert "GUID sys_id PK" in diagram
    assert "string name" in diagram
    assert "reference data_relationship FK" in diagram


def test_diagram_hides_audit_fields_from_entity_block() -> None:
    diagram = MermaidErdEmitter().diagram(_graph())
    assert "sys_created_by" not in diagram


def test_diagram_omits_block_for_table_without_key_fields() -> None:
    # data_relationship has no fields -> no entity block, only edge lines.
    diagram = MermaidErdEmitter().diagram(_graph())
    assert "data_relationship {" not in diagram


def test_diagram_braces_are_balanced() -> None:
    # Edge cardinalities ('}o--||') carry braces too, so count block lines,
    # not raw characters: every entity-open line needs its closing brace.
    lines = MermaidErdEmitter().diagram(_multi_entity_graph()).splitlines()
    opens = sum(1 for line in lines if line.endswith(" {"))
    closes = sum(1 for line in lines if line == "    }")
    assert opens == 2  # one block per entity with fields
    assert opens == closes


def test_diagram_every_line_matches_er_grammar() -> None:
    diagram = MermaidErdEmitter().diagram(_multi_entity_graph())
    for line in diagram.splitlines():
        assert any(p.fullmatch(line) for p in _ER_LINE_GRAMMAR), f"unparseable line: {line!r}"


def test_diagram_empty_graph_renders_header_only() -> None:
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )
    assert MermaidErdEmitter().diagram(graph) == "erDiagram"


def test_diagram_audit_only_table_omits_entity_block() -> None:
    # All fields are hidden sys_* audit columns (no sys_id) -> no attrs -> no block.
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(
            TableDef(
                name="audit_only",
                label="Audit only",
                scope="sn_grc_doc_design",
                fields=(
                    FieldDef(name="sys_created_by", label="Created by", type="string"),
                    FieldDef(name="sys_updated_by", label="Updated by", type="string"),
                ),
            ),
        ),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )
    assert MermaidErdEmitter().diagram(graph) == "erDiagram"


def test_diagram_self_referencing_edge_renders() -> None:
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(TableDef(name="task_table", label="Task", scope="sn_grc_doc_design"),),
        reference_edges=(
            ReferenceEdge(
                from_table="task_table",
                field="parent",
                to_table="task_table",
                cross_scope=False,
            ),
        ),
        inheritance_edges=(),
        relationship_edges=(),
    )
    diagram = MermaidErdEmitter().diagram(graph)
    assert '    task_table }o--|| task_table : "parent"' in diagram


def test_diagram_duplicate_edges_render_twice() -> None:
    # Pins current behavior: the emitter does not deduplicate edges.
    edge = ReferenceEdge(
        from_table="content_config",
        field="data_relationship",
        to_table="data_relationship",
        cross_scope=False,
    )
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(
            TableDef(name="content_config", label="Content", scope="sn_grc_doc_design"),
            TableDef(name="data_relationship", label="Data rel", scope="sn_grc_doc_design"),
        ),
        reference_edges=(edge, edge),
        inheritance_edges=(),
        relationship_edges=(),
    )
    diagram = MermaidErdEmitter().diagram(graph)
    assert diagram.count('content_config }o--|| data_relationship : "data_relationship"') == 2


def test_token_empty_type_falls_back() -> None:
    assert _token("", "field") == "field"
