# tests/schema/test_mindmap_emitter.py
# Tests for the Mermaid mindmap emitter.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Emitter renders a mindmap block + grouped catalog."""

from datetime import UTC, datetime

from nexus.schema.catalog import Domain, MindmapCatalog, Section, TableDescription
from nexus.schema.mindmap_emitter import MindmapEmitter


def _catalog() -> MindmapCatalog:
    return MindmapCatalog(
        instance_id="alectri",
        area_key="bcm",
        generated_at=datetime(2026, 6, 8, tzinfo=UTC),
        display="Business Continuity Management",
        sections=(
            Section(
                name="Planning",
                domains=(
                    Domain(
                        name="Plan Management",
                        tables=(
                            TableDescription(
                                table="sn_bcp_plan",
                                label="Plan",
                                description="Stores BC plans and recovery objectives.",
                                source="ai",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_render_contains_mermaid_mindmap_block() -> None:
    out = MindmapEmitter().render(_catalog())
    assert "```mermaid" in out
    assert "mindmap" in out
    assert "root((Business Continuity Management))" in out


def test_render_mindmap_leaf_embeds_label_table_and_description() -> None:
    out = MindmapEmitter().render(_catalog())
    assert (
        'sn_bcp_plan["`**Plan** [sn_bcp_plan]: Stores BC plans and recovery objectives.`"]' in out
    )


def test_render_grouped_catalog_has_section_domain_and_description() -> None:
    out = MindmapEmitter().render(_catalog())
    assert "## Planning" in out
    assert "### Plan Management" in out
    assert "**Plan** [sn_bcp_plan]: Stores BC plans and recovery objectives." in out


def test_diagram_returns_bare_mindmap_source() -> None:
    diagram = MindmapEmitter().diagram(_catalog())
    assert diagram.startswith("mindmap")
    assert "root((Business Continuity Management))" in diagram
    assert "    Planning" in diagram
    assert "      Plan Management" in diagram
    assert (
        '        sn_bcp_plan["`**Plan** [sn_bcp_plan]: '
        'Stores BC plans and recovery objectives.`"]'
    ) in diagram
    assert "```" not in diagram


def test_diagram_neutralizes_markdown_string_delimiters() -> None:
    catalog = MindmapCatalog(
        instance_id="i",
        area_key="a",
        generated_at=datetime(2026, 6, 8, tzinfo=UTC),
        display="Root (with parens)",
        sections=(
            Section(
                name="Sec",
                domains=(
                    Domain(
                        name="Grp",
                        tables=(
                            TableDescription(
                                table="sn_x",
                                label="La`bel",
                                description='Stores "quoted" and `backtick` text',
                                source="ai",
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    diagram = MindmapEmitter().diagram(catalog)
    # root parens stripped so the ((...)) shape is not broken
    assert "root((Root with parens))" in diagram
    # backticks/quotes inside the leaf replaced so the markdown string stays valid
    assert "`backtick`" not in diagram
    assert '"quoted"' not in diagram
    assert "sn_x[\"`**La'bel** [sn_x]: Stores 'quoted' and 'backtick' text`\"]" in diagram
