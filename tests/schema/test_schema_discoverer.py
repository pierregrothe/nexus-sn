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
            {
                "sys_id": "TASK",
                "name": "task",
                "label": "Task",
                "super_class": "",
                "sys_scope": _ref("GLOBAL"),
            },
        ],
        "sys_dictionary": [
            {
                "name": "sn_grc_doc_design_data_rel_mapping",
                "element": "data_relationship",
                "column_label": "Data relationship",
                "internal_type": "reference",
                "reference": _ref("sn_grc_doc_design_data_relationship"),
                "mandatory": "true",
            },
            {
                "name": "sn_grc_doc_design_data_relationship",
                "element": "name",
                "column_label": "Name",
                "internal_type": "string",
                "reference": "",
                "mandatory": "false",
            },
        ],
        "sys_relationship": [
            {
                "name": "rel",
                "apply_to": _ref("sn_grc_doc_design_data_relationship"),
                "query_from": _ref("sn_grc_doc_design_data_rel_mapping"),
            },
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
async def test_discover_field_uses_internal_type() -> None:
    graph = await _disc(_seed()).discover("alectri", "dd")
    table = next(t for t in graph.tables if t.name == "sn_grc_doc_design_data_relationship")
    name_field = next(f for f in table.fields if f.name == "name")
    assert name_field.type == "string"


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
    inh = next(
        e for e in graph.inheritance_edges if e.table == "sn_grc_doc_design_data_relationship"
    )
    assert inh.extends == "task"
    assert inh.cross_scope is True
    assert any(t.name == "task" and t.is_neighbor for t in graph.tables)


class _ExtraDictRowClient(FakeServiceNowClient):
    """Fake that returns one out-of-scope sys_dictionary row on every page."""

    async def list_records(
        self,
        table: str,
        query: str = "",
        limit: int = 1000,
        offset: int = 0,
        fields: str = "",
        display_value: str = "false",
    ) -> list[dict[str, object]]:
        """Append an unrequested 'task' dictionary row to query results."""
        rows = await super().list_records(
            table,
            query=query,
            limit=limit,
            offset=offset,
            fields=fields,
            display_value=display_value,
        )
        if table == "sys_dictionary":
            rows.append(
                {
                    "name": "task",
                    "element": "number",
                    "column_label": "Number",
                    "reference": "",
                    "mandatory": "false",
                }
            )
        return rows


class _ExtraDbObjectRowClient(FakeServiceNowClient):
    """Fake that returns one malformed sys_db_object row on every page."""

    async def list_records(
        self,
        table: str,
        query: str = "",
        limit: int = 1000,
        offset: int = 0,
        fields: str = "",
        display_value: str = "false",
    ) -> list[dict[str, object]]:
        """Append an unrequested out-of-scope table row to query results."""
        rows = await super().list_records(
            table,
            query=query,
            limit=limit,
            offset=offset,
            fields=fields,
            display_value=display_value,
        )
        if table == "sys_db_object":
            rows.append(
                {
                    "sys_id": "TASK",
                    "name": "task",
                    "label": "Task",
                    "super_class": "",
                    "sys_scope": _ref("GLOBAL"),
                }
            )
        return rows


@pytest.mark.asyncio
async def test_discover_skips_db_object_rows_for_unresolved_scopes() -> None:
    # A misbehaving server returns a table row whose scope was never
    # requested; the discoverer must not classify it as in-scope.
    disc = SchemaDiscoverer(
        _ExtraDbObjectRowClient(_seed()),
        areas=_AREAS,
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )
    graph = await disc.discover("alectri", "dd")
    assert all(t.name != "task" for t in graph.tables if not t.is_neighbor)


@pytest.mark.asyncio
async def test_discover_skips_dict_rows_for_out_of_scope_tables() -> None:
    # A misbehaving server returns a dictionary row for a table outside the
    # area; the discoverer must drop it.
    disc = SchemaDiscoverer(
        _ExtraDictRowClient(_seed()),
        areas=_AREAS,
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )
    graph = await disc.discover("alectri", "dd")
    assert not any(e.from_table == "task" for e in graph.reference_edges)
    assert all(t.name != "task" or t.is_neighbor for t in graph.tables)


@pytest.mark.asyncio
async def test_discover_more_than_forty_tables_batches_dictionary_queries() -> None:
    n = 41  # one over the IN-batch size of 40 -> two sys_dictionary queries
    seed: dict[str, list[dict[str, object]]] = {
        "sys_scope": [{"sys_id": "SCID", "scope": "sn_grc_doc_design"}],
        "sys_db_object": [
            {
                "sys_id": f"T{i}",
                "name": f"sn_grc_doc_design_t{i:02d}",
                "label": f"Table {i}",
                "super_class": "",
                "sys_scope": _ref("SCID"),
            }
            for i in range(n)
        ],
        "sys_dictionary": [
            {
                "name": f"sn_grc_doc_design_t{i:02d}",
                "element": "u_field",
                "column_label": "Field",
                "reference": "",
                "mandatory": "false",
            }
            for i in range(n)
        ],
        "sys_relationship": [],
    }
    graph = await _disc(seed).discover("alectri", "dd")
    in_scope = [t for t in graph.tables if not t.is_neighbor]
    assert len(in_scope) == n
    # Each table owns exactly one field: batch queries must not duplicate rows.
    assert all(len(t.fields) == 1 for t in in_scope)


@pytest.mark.asyncio
async def test_discover_paginates_dictionary_rows_beyond_page_limit() -> None:
    n_fields = 5001  # one over the 5000-row page limit -> two pages
    seed = _seed()
    seed["sys_dictionary"] = [
        {
            "name": "sn_grc_doc_design_data_relationship",
            "element": f"u_f{i:04d}",
            "column_label": f"Field {i}",
            "reference": "",
            "mandatory": "false",
        }
        for i in range(n_fields)
    ]
    graph = await _disc(seed).discover("alectri", "dd")
    table = next(t for t in graph.tables if t.name == "sn_grc_doc_design_data_relationship")
    assert len(table.fields) == n_fields


@pytest.mark.asyncio
async def test_discover_empty_scope_skips_relationship_query() -> None:
    seed = _seed()
    seed["sys_db_object"] = []  # scope resolves but owns zero tables
    client = FakeServiceNowClient(seed)
    disc = SchemaDiscoverer(client, areas=_AREAS, clock=lambda: datetime(2026, 6, 8, tzinfo=UTC))
    graph = await disc.discover("alectri", "dd")
    assert graph.relationship_edges == ()
    assert all(table != "sys_relationship" for table, _ in client.calls)


@pytest.mark.asyncio
async def test_discover_relationship_rows_deduped_across_passes() -> None:
    # The seeded row's apply_to AND query_from are both in scope, so it
    # matches both batched passes -- it must still yield exactly one edge.
    graph = await _disc(_seed()).discover("alectri", "dd")
    assert len(graph.relationship_edges) == 1


@pytest.mark.asyncio
async def test_discover_with_bridge_targets_narrows_to_neighborhood() -> None:
    area = SchemaArea(
        key="b",
        display="B",
        scopes=(ScopeRef("sn_grc_doc_design", "DD"),),
        bridge_targets=("sn_grc_doc_design_data_relationship",),
    )
    disc = SchemaDiscoverer(
        FakeServiceNowClient(_seed()),
        areas={"b": area},
        clock=lambda: datetime(2026, 6, 8, tzinfo=UTC),
    )
    graph = await disc.discover("alectri", "b")
    names = {t.name for t in graph.tables}
    assert "sn_grc_doc_design_data_rel_mapping" in names  # references the target
    assert "sn_grc_doc_design_data_relationship" in names  # the bridge target
