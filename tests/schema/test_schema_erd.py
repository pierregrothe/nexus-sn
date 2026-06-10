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

# Grammar for every line diagram() may emit. A future cardinality is a
# one-line addition here.
_ER_LINE_GRAMMAR: tuple[re.Pattern[str], ...] = (
    re.compile(r"erDiagram"),  # header
    re.compile(r"    \w+ \{"),  # entity open
    re.compile(r"        \w+ \w+( PK| FK)?"),  # attribute
    re.compile(r"    \}"),  # entity close
    re.compile(r'    \w+ \}o--\|\| \w+ : "[^"]+"'),  # reference edge
    re.compile(r'    \w+ \}o--o\{ \w+ : "[^"]+"'),  # list-reference edge
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


def test_diagram_list_reference_renders_many_to_many() -> None:
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="cmdb-bcm",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_bcp",),
        tables=(
            TableDef(name="sn_bcp_plan", label="Plan", scope="sn_bcp"),
            TableDef(name="sys_user", label="User", scope="", is_neighbor=True),
        ),
        reference_edges=(
            ReferenceEdge(
                from_table="sn_bcp_plan",
                field="contributors",
                to_table="sys_user",
                cross_scope=True,
                is_list=True,
            ),
        ),
        inheritance_edges=(),
        relationship_edges=(),
    )
    diagram = MermaidErdEmitter().diagram(graph)
    assert '    sn_bcp_plan }o--o{ sys_user : "contributors"' in diagram
    assert "}o--||" not in diagram


def test_diagram_tables_emitted_in_sorted_order() -> None:
    # Tables are seeded out of alphabetical order; entity blocks must sort.
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(
            TableDef(
                name="zeta_table",
                label="Zeta",
                scope="sn_grc_doc_design",
                fields=(FieldDef(name="sys_id", label="Sys ID", type="GUID"),),
            ),
            TableDef(
                name="alpha_table",
                label="Alpha",
                scope="sn_grc_doc_design",
                fields=(FieldDef(name="sys_id", label="Sys ID", type="GUID"),),
            ),
        ),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )
    diagram = MermaidErdEmitter().diagram(graph)
    opens = [line for line in diagram.splitlines() if line.endswith(" {")]
    assert opens == ["    alpha_table {", "    zeta_table {"]


def test_diagram_entity_attributes_sorted_within_sections() -> None:
    # Fields are seeded out of order; PK stays first, business and FK
    # sections each sort alphabetically by field name.
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(
            TableDef(
                name="plan_table",
                label="Plan",
                scope="sn_grc_doc_design",
                fields=(
                    FieldDef(name="zeta", label="Zeta", type="string"),
                    FieldDef(
                        name="ref_b", label="Ref B", type="reference", reference_target="b_table"
                    ),
                    FieldDef(name="sys_id", label="Sys ID", type="GUID"),
                    FieldDef(name="alpha", label="Alpha", type="string"),
                    FieldDef(
                        name="ref_a", label="Ref A", type="reference", reference_target="a_table"
                    ),
                ),
            ),
        ),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )
    lines = MermaidErdEmitter().diagram(graph).splitlines()
    attrs = [line.strip() for line in lines[lines.index("    plan_table {") + 1 : -1]]
    assert attrs == [
        "GUID sys_id PK",
        "string alpha",
        "string zeta",
        "reference ref_a FK",
        "reference ref_b FK",
    ]


def test_diagram_rendered_twice_is_byte_identical() -> None:
    emitter = MermaidErdEmitter()
    graph = _multi_entity_graph()
    assert emitter.diagram(graph) == emitter.diagram(graph)


def test_token_empty_type_falls_back() -> None:
    assert _token("", "field") == "field"


def _two_scope_graph() -> SchemaGraph:
    """Two scopes, a neighbor, a cross-scope ref edge, and an inheritance edge."""
    return SchemaGraph(
        instance_id="alectri",
        area_key="bcm",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_bcm", "sn_bcp"),
        tables=(
            TableDef(
                name="sn_bcm_impact",
                label="Impact",
                scope="sn_bcm",
                fields=(
                    FieldDef(name="sys_id", label="Sys ID", type="GUID"),
                    FieldDef(
                        name="plan", label="Plan", type="reference", reference_target="sn_bcp_plan"
                    ),
                ),
            ),
            TableDef(
                name="sn_bcm_orphan",
                label="Orphan",
                scope="sn_bcm",
                fields=(FieldDef(name="sys_id", label="Sys ID", type="GUID"),),
            ),
            TableDef(
                name="sn_bcp_plan",
                label="Plan",
                scope="sn_bcp",
                fields=(FieldDef(name="sys_id", label="Sys ID", type="GUID"),),
            ),
            TableDef(
                name="sn_bcp_task",
                label="Task",
                scope="sn_bcp",
                fields=(FieldDef(name="sys_id", label="Sys ID", type="GUID"),),
            ),
            TableDef(name="cmdb_ci", label="CI", scope="", is_neighbor=True),
        ),
        reference_edges=(
            ReferenceEdge(
                from_table="sn_bcm_impact",
                field="plan",
                to_table="sn_bcp_plan",
                cross_scope=True,
            ),
            ReferenceEdge(
                from_table="sn_bcp_plan", field="ci", to_table="cmdb_ci", cross_scope=True
            ),
        ),
        inheritance_edges=(
            InheritanceEdge(table="sn_bcp_task", extends="sn_bcp_plan", cross_scope=False),
        ),
        relationship_edges=(),
    )


def test_group_diagrams_splits_by_scope() -> None:
    groups = MermaidErdEmitter().group_diagrams(_two_scope_graph(), {})
    assert [g.key for g in groups] == ["sn_bcm", "sn_bcp"]
    assert "sn_bcm_impact {" in groups[0].source
    assert "sn_bcm_orphan {" in groups[0].source
    assert "sn_bcp_plan {" in groups[1].source
    assert "sn_bcp_task {" in groups[1].source
    assert "sn_bcm_impact" not in groups[1].source
    assert "sn_bcp_task" not in groups[0].source


def test_group_diagrams_assigns_cross_edge_to_from_group_with_bare_target() -> None:
    bcm, bcp = MermaidErdEmitter().group_diagrams(_two_scope_graph(), {})
    line = '    sn_bcm_impact }o--|| sn_bcp_plan : "plan"'
    assert line in bcm.source
    assert line not in bcp.source
    # The target appears bare in the from-group: edge line only, no block.
    assert "sn_bcp_plan {" not in bcm.source


def test_group_diagrams_inheritance_edge_in_child_group() -> None:
    bcm, bcp = MermaidErdEmitter().group_diagrams(_two_scope_graph(), {})
    line = '    sn_bcp_plan ||--|| sn_bcp_task : "extends"'
    assert line in bcp.source
    assert line not in bcm.source


def test_group_diagrams_neighbor_renders_bare_only_in_referencing_group() -> None:
    bcm, bcp = MermaidErdEmitter().group_diagrams(_two_scope_graph(), {})
    assert '    sn_bcp_plan }o--|| cmdb_ci : "ci"' in bcp.source
    assert "cmdb_ci {" not in bcp.source
    assert "cmdb_ci" not in bcm.source


def test_group_diagrams_orders_groups_by_scope_key() -> None:
    # Scopes are seeded out of alphabetical order; group order must sort.
    graph = SchemaGraph(
        instance_id="alectri",
        area_key="bcm",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("z_scope", "a_scope"),
        tables=(
            TableDef(name="z_table", label="Z", scope="z_scope"),
            TableDef(name="a_table", label="A", scope="a_scope"),
        ),
        reference_edges=(),
        inheritance_edges=(),
        relationship_edges=(),
    )
    groups = MermaidErdEmitter().group_diagrams(graph, {})
    assert [g.key for g in groups] == ["a_scope", "z_scope"]


def test_group_diagrams_label_falls_back_to_scope_key() -> None:
    groups = MermaidErdEmitter().group_diagrams(_two_scope_graph(), {"sn_bcm": "BCM Core"})
    assert [g.label for g in groups] == ["BCM Core", "sn_bcp"]


def test_group_diagrams_skips_edge_with_unknown_from_table() -> None:
    # Defensive: edges owned by an unknown table or a neighbor land nowhere.
    graph = _two_scope_graph().model_copy(
        update={
            "reference_edges": (
                ReferenceEdge(
                    from_table="ghost", field="x", to_table="sn_bcp_plan", cross_scope=False
                ),
                ReferenceEdge(
                    from_table="cmdb_ci", field="y", to_table="sn_bcp_plan", cross_scope=True
                ),
            ),
            "inheritance_edges": (
                InheritanceEdge(table="ghost_child", extends="sn_bcp_plan", cross_scope=False),
                InheritanceEdge(table="cmdb_ci", extends="sn_bcp_plan", cross_scope=True),
            ),
        }
    )
    for group in MermaidErdEmitter().group_diagrams(graph, {}):
        assert "ghost" not in group.source
        assert "cmdb_ci" not in group.source


def test_group_diagrams_every_line_matches_er_grammar() -> None:
    for group in MermaidErdEmitter().group_diagrams(_two_scope_graph(), {}):
        for line in group.source.splitlines():
            assert any(p.fullmatch(line) for p in _ER_LINE_GRAMMAR), f"unparseable line: {line!r}"


def test_render_grouped_emits_one_section_per_group() -> None:
    out = MermaidErdEmitter().render_grouped(_two_scope_graph(), {"sn_bcm": "BCM Core"})
    headings = [line for line in out.splitlines() if line.startswith("## ")]
    assert headings == ["## BCM Core", "## sn_bcp", "## Cross-scope bridges", "## Fields"]
    assert out.count("```mermaid") == 2


def test_render_grouped_keeps_bridges_and_fields_once() -> None:
    out = MermaidErdEmitter().render_grouped(_two_scope_graph(), {})
    assert out.count("## Cross-scope bridges") == 1
    assert out.count("## Fields") == 1
    assert "- sn_bcm_impact.plan -> sn_bcp_plan" in out


def test_render_grouped_edgeless_table_still_listed() -> None:
    # sn_bcm_orphan has no edges; it still shows in its group diagram and
    # in the field appendix.
    out = MermaidErdEmitter().render_grouped(_two_scope_graph(), {})
    assert "sn_bcm_orphan {" in out
    assert "### sn_bcm_orphan -- Orphan" in out
