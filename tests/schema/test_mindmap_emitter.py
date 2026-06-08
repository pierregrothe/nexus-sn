# tests/schema/test_mindmap_emitter.py
# Tests for the Mermaid mindmap emitter.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Emitter renders a mindmap block + grouped catalog."""

from datetime import UTC, datetime

from nexus.schema.catalog import Domain, MindmapCatalog, TableDescription
from nexus.schema.mindmap_emitter import MindmapEmitter


def _catalog() -> MindmapCatalog:
    return MindmapCatalog(
        instance_id="alectri",
        area_key="bcm",
        generated_at=datetime(2026, 6, 8, tzinfo=UTC),
        display="Business Continuity Management",
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
    )


def test_render_contains_mermaid_mindmap_block() -> None:
    out = MindmapEmitter().render(_catalog())
    assert "```mermaid" in out
    assert "mindmap" in out
    assert "root((Business Continuity Management))" in out


def test_render_mindmap_leaf_shows_label_and_table() -> None:
    out = MindmapEmitter().render(_catalog())
    assert "Plan -- sn_bcp_plan" in out


def test_render_grouped_catalog_has_domain_and_description() -> None:
    out = MindmapEmitter().render(_catalog())
    assert "## Plan Management" in out
    assert "**Plan** [sn_bcp_plan]: Stores BC plans and recovery objectives." in out
