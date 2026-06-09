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
        ),
        relationship_edges=(
            RelationshipEdge(name="r", apply_to="sn_bcp_recovery_task", query_from="sn_bcp_plan"),
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
