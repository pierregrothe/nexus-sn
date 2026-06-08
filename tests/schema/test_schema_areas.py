# tests/schema/test_schema_areas.py
# Tests for the schema area registry.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify seeded areas expose the validated scopes."""

from nexus.schema.areas import DEFAULT_AREAS, DOC_DESIGNER, SchemaArea, ScopeRef


def test_default_areas_contains_three_seeded_areas() -> None:
    assert set(DEFAULT_AREAS) == {"doc-designer", "bcm", "cmdb-bcm"}


def test_doc_designer_scopes_are_validated_set() -> None:
    keys = [s.scope for s in DOC_DESIGNER.scopes]
    assert keys == ["sn_grc_doc_design", "sn_grc_rel_config"]


def test_schema_area_default_neighbor_hops_is_one() -> None:
    area = SchemaArea(key="x", display="X", scopes=(ScopeRef("a", "A"),))
    assert area.neighbor_hops == 1
