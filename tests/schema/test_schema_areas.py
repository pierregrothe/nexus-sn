# tests/schema/test_schema_areas.py
# Tests for the schema area registry.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify seeded areas expose the validated scopes."""

from nexus.schema.areas import DEFAULT_AREAS, DOC_DESIGNER, HAM_ITSM


def test_default_areas_contains_four_seeded_areas() -> None:
    assert set(DEFAULT_AREAS) == {"doc-designer", "bcm", "cmdb-bcm", "ham-itsm"}


def test_doc_designer_scopes_are_validated_set() -> None:
    keys = [s.key for s in DOC_DESIGNER.scopes]
    assert keys == ["sn_grc_doc_design", "sn_grc_rel_config"]


def test_ham_itsm_scope_and_bridge_target() -> None:
    assert [s.key for s in HAM_ITSM.scopes] == ["sn_hamp"]
    assert HAM_ITSM.bridge_targets == ("cmdb_ci",)
