# tests/schema/test_schema_models.py
# Tests for schema Pydantic models.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Verify model immutability and the cross_scope_edges helper."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.schema.models import ReferenceEdge, SchemaGraph, TableDef


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="doc-designer",
        discovered_at=datetime(2026, 6, 8, tzinfo=UTC),
        scope_keys=("sn_grc_doc_design",),
        tables=(TableDef(name="t", label="T", scope="sn_grc_doc_design"),),
        reference_edges=(
            ReferenceEdge(from_table="a", field="f1", to_table="b", cross_scope=False),
            ReferenceEdge(from_table="a", field="f2", to_table="z", cross_scope=True),
        ),
        inheritance_edges=(),
        relationship_edges=(),
    )


def test_schema_graph_cross_scope_edges_filters_to_cross_scope() -> None:
    edges = _graph().cross_scope_edges()
    assert [e.field for e in edges] == ["f2"]


def test_table_def_is_frozen() -> None:
    table = TableDef(name="t", label="T", scope="s")
    with pytest.raises(ValidationError):
        setattr(table, "name", "other")


def test_reference_edge_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        ReferenceEdge(**{"from_table": "a", "field": "f", "to_table": "b", "cross_scope": False, "bogus": 1})
