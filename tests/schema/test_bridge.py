# tests/schema/test_bridge.py
# Tests for bridge_subgraph filtering.
# Author: Pierre Grothe
# Date: 2026-06-09
"""bridge_subgraph narrows a graph to the neighborhood around target tables."""

from datetime import UTC, datetime

from nexus.schema.bridge import bridge_subgraph
from nexus.schema.models import (
    InheritanceEdge,
    ReferenceEdge,
    RelationshipEdge,
    SchemaGraph,
    TableDef,
)


def _graph() -> SchemaGraph:
    return SchemaGraph(
        instance_id="alectri",
        area_key="cmdb-bcm",
        discovered_at=datetime(2026, 6, 9, tzinfo=UTC),
        scope_keys=("sn_bcp",),
        tables=(
            TableDef(name="sn_bcp_recovery_task", label="Recovery task", scope="sn_bcp"),
            TableDef(name="sn_bcp_recovery_team", label="Recovery team", scope="sn_bcp"),
            TableDef(name="sn_bcp_plan", label="Plan", scope="sn_bcp"),
            TableDef(name="sn_bcp_unrelated", label="Unrelated", scope="sn_bcp"),
            TableDef(name="sn_bcp_orphan_child", label="Orphan child", scope="sn_bcp"),
            TableDef(name="cmdb_ci", label="CI", scope="", is_neighbor=True),
        ),
        reference_edges=(
            ReferenceEdge(
                from_table="sn_bcp_recovery_task",
                field="configuration_item",
                to_table="cmdb_ci",
                cross_scope=True,
            ),
            ReferenceEdge(
                from_table="sn_bcp_recovery_task",
                field="plan",
                to_table="sn_bcp_plan",
                cross_scope=False,
            ),
            ReferenceEdge(
                from_table="sn_bcp_recovery_team",
                field="task",
                to_table="sn_bcp_recovery_task",
                cross_scope=False,
            ),
            ReferenceEdge(
                from_table="sn_bcp_unrelated",
                field="plan",
                to_table="sn_bcp_plan",
                cross_scope=False,
            ),
        ),
        inheritance_edges=(
            InheritanceEdge(
                table="sn_bcp_recovery_team", extends="sn_bcp_recovery_task", cross_scope=False
            ),
            InheritanceEdge(
                table="sn_bcp_orphan_child", extends="sn_bcp_recovery_task", cross_scope=False
            ),
        ),
        relationship_edges=(
            RelationshipEdge(name="r", apply_to="sn_bcp_recovery_task", query_from="sn_bcp_plan"),
            RelationshipEdge(name="r2", apply_to="sn_bcp_unrelated", query_from="sn_bcp_plan"),
        ),
    )


def test_bridge_subgraph_keeps_target_and_referencing_table() -> None:
    names = {t.name for t in bridge_subgraph(_graph(), ("cmdb_ci",)).tables}
    assert "cmdb_ci" in names
    assert "sn_bcp_recovery_task" in names


def test_bridge_subgraph_keeps_one_hop_outgoing_neighbor() -> None:
    names = {t.name for t in bridge_subgraph(_graph(), ("cmdb_ci",)).tables}
    assert "sn_bcp_plan" in names  # recovery_task -> plan, one hop out


def test_bridge_subgraph_keeps_one_hop_incoming_neighbor() -> None:
    names = {t.name for t in bridge_subgraph(_graph(), ("cmdb_ci",)).tables}
    assert "sn_bcp_recovery_team" in names  # recovery_team -> recovery_task, one hop in


def test_bridge_subgraph_drops_unrelated_table() -> None:
    names = {t.name for t in bridge_subgraph(_graph(), ("cmdb_ci",)).tables}
    assert "sn_bcp_unrelated" not in names


def test_bridge_subgraph_keeps_only_edges_among_kept_tables() -> None:
    graph = bridge_subgraph(_graph(), ("cmdb_ci",))
    pairs = {(e.from_table, e.to_table) for e in graph.reference_edges}
    assert ("sn_bcp_recovery_task", "cmdb_ci") in pairs
    assert ("sn_bcp_unrelated", "sn_bcp_plan") not in pairs  # both filtered out
    assert graph.inheritance_edges[0].table == "sn_bcp_recovery_team"
    assert graph.relationship_edges[0].apply_to == "sn_bcp_recovery_task"


def test_bridge_subgraph_absent_target_returns_empty_graph() -> None:
    # Pins current behavior: an unknown target silently yields an empty graph.
    graph = bridge_subgraph(_graph(), ("no_such_table",))
    assert graph.tables == ()
    assert graph.reference_edges == ()
    assert graph.inheritance_edges == ()
    assert graph.relationship_edges == ()


def test_bridge_subgraph_target_with_no_referencing_tables_keeps_bare_target() -> None:
    # Nothing references sn_bcp_unrelated -> only the bare target survives.
    graph = bridge_subgraph(_graph(), ("sn_bcp_unrelated",))
    assert {t.name for t in graph.tables} == {"sn_bcp_unrelated"}
    assert graph.reference_edges == ()


def test_bridge_subgraph_drops_inheritance_only_child() -> None:
    # Documents the reference-edges-only walk: a child connected to a seed
    # table solely via inheritance is not pulled into the bridge.
    graph = bridge_subgraph(_graph(), ("cmdb_ci",))
    assert "sn_bcp_orphan_child" not in {t.name for t in graph.tables}
    assert all(e.table != "sn_bcp_orphan_child" for e in graph.inheritance_edges)


def test_bridge_subgraph_filters_relationship_edges() -> None:
    # r2 touches the dropped sn_bcp_unrelated table -> filtered out.
    names = {e.name for e in bridge_subgraph(_graph(), ("cmdb_ci",)).relationship_edges}
    assert "r" in names
    assert "r2" not in names
