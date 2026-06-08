# tests/schema/test_schema_discoverer.py
# Tests for SchemaDiscoverer against the FakeServiceNowClient.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Discovery transforms seeded dictionary rows into a SchemaGraph."""

from datetime import UTC, datetime

import pytest

from nexus.schema.areas import SchemaArea, ScopeRef
from nexus.schema.discoverer import SchemaDiscoverer, cell
from nexus.schema.errors import AreaNotFoundError, ScopeNotFoundError
from tests.fakes.fake_sn_client import FakeServiceNowClient

_AREA = SchemaArea(key="dd", display="DD", scopes=(ScopeRef("sn_grc_doc_design", "DD"),))
_AREAS = {"dd": _AREA}


def _ref(value: str) -> dict[str, str]:
    return {"link": f"x/{value}", "value": value}


def _seed() -> dict[str, list[dict[str, object]]]:
    return {
        "sys_scope": [{"sys_id": "SCID", "scope": "sn_grc_doc_design"}],
        "sys_db_object": [
            {
                "sys_id": "T1",
                "name": "sn_grc_doc_design_data_rel_mapping",
                "label": "Content configuration",
                "super_class": "",
                "sys_scope": _ref("SCID"),
            },
            {
                "sys_id": "T2",
                "name": "sn_grc_doc_design_data_relationship",
                "label": "Data relationship",
                "super_class": "",
                "sys_scope": _ref("SCID"),
            },
            {"sys_id": "TASK", "name": "task", "label": "Task", "super_class": "",
             "sys_scope": _ref("GLOBAL")},
        ],
        "sys_dictionary": [
            {"name": "sn_grc_doc_design_data_rel_mapping", "element": "data_relationship",
             "column_label": "Data relationship", "reference": _ref("sn_grc_doc_design_data_relationship"),
             "mandatory": "true"},
            {"name": "sn_grc_doc_design_data_relationship", "element": "name",
             "column_label": "Name", "reference": "", "mandatory": "false"},
        ],
        "sys_relationship": [
            {"name": "rel", "apply_to": _ref("sn_grc_doc_design_data_relationship"),
             "query_from": _ref("sn_grc_doc_design_data_rel_mapping")},
        ],
    }


def _disc(seed: dict[str, list[dict[str, object]]]) -> SchemaDiscoverer:
    return SchemaDiscoverer(
        FakeServiceNowClient(seed),
        areas=_AREAS,
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )


def test_cell_extracts_value_from_reference_dict() -> None:
    assert cell({"f": {"link": "x", "value": "abc"}}, "f") == "abc"


def test_cell_returns_plain_string() -> None:
    assert cell({"f": "plain"}, "f") == "plain"


def test_cell_missing_key_returns_empty() -> None:
    assert cell({}, "f") == ""


@pytest.mark.asyncio
async def test_discover_unknown_area_raises() -> None:
    with pytest.raises(AreaNotFoundError):
        await _disc(_seed()).discover("alectri", "nope")


@pytest.mark.asyncio
async def test_discover_no_scope_resolves_raises() -> None:
    seed = _seed()
    seed["sys_scope"] = []
    with pytest.raises(ScopeNotFoundError):
        await _disc(seed).discover("alectri", "dd")


@pytest.mark.asyncio
async def test_discover_builds_reference_edge_with_target_name() -> None:
    graph = await _disc(_seed()).discover("alectri", "dd")
    edge = next(e for e in graph.reference_edges if e.field == "data_relationship")
    assert edge.from_table == "sn_grc_doc_design_data_rel_mapping"
    assert edge.to_table == "sn_grc_doc_design_data_relationship"
    assert edge.cross_scope is False


@pytest.mark.asyncio
async def test_discover_classifies_in_scope_tables_only() -> None:
    graph = await _disc(_seed()).discover("alectri", "dd")
    in_scope = {t.name for t in graph.tables if not t.is_neighbor}
    assert in_scope == {
        "sn_grc_doc_design_data_rel_mapping",
        "sn_grc_doc_design_data_relationship",
    }


@pytest.mark.asyncio
async def test_discover_sets_discovered_at_from_clock() -> None:
    graph = await _disc(_seed()).discover("alectri", "dd")
    assert graph.discovered_at == datetime(2026, 6, 8, tzinfo=UTC)


@pytest.mark.asyncio
async def test_discover_builds_relationship_edge() -> None:
    graph = await _disc(_seed()).discover("alectri", "dd")
    assert graph.relationship_edges[0].name == "rel"


@pytest.mark.asyncio
async def test_discover_inheritance_edge_marks_neighbor_parent() -> None:
    seed = _seed()
    for row in seed["sys_db_object"]:
        if row["name"] == "sn_grc_doc_design_data_relationship":
            row["super_class"] = _ref("TASK")
    graph = await _disc(seed).discover("alectri", "dd")
    inh = next(e for e in graph.inheritance_edges if e.table == "sn_grc_doc_design_data_relationship")
    assert inh.extends == "task"
    assert inh.cross_scope is True
    assert any(t.name == "task" and t.is_neighbor for t in graph.tables)
