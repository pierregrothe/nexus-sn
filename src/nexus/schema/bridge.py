# src/nexus/schema/bridge.py
# Narrows a SchemaGraph to the neighborhood bridging to target tables.
# Author: Pierre Grothe
# Date: 2026-06-09
"""bridge_subgraph: focus a SchemaGraph on its bridge to target tables."""

from __future__ import annotations

from nexus.schema.models import SchemaGraph

__all__ = ["bridge_subgraph"]


def bridge_subgraph(graph: SchemaGraph, targets: tuple[str, ...]) -> SchemaGraph:
    """Narrow a graph to the tables that bridge to the given target tables.

    Keeps the target tables, every table with a reference edge to a target, and
    those tables' immediate reference neighbors (one hop), plus the edges among
    the kept set. Everything else is dropped, yielding a focused "how X connects
    to Y" map instead of the full area.

    Args:
        graph: The full discovered graph.
        targets: Target table names on the far side of the bridge (e.g.
            ``("cmdb_ci",)``).

    Returns:
        A new SchemaGraph containing only the bridge neighborhood.
    """
    target_set = set(targets)
    seed = {e.from_table for e in graph.reference_edges if e.to_table in target_set}
    keep = seed | target_set
    for edge in graph.reference_edges:
        if edge.from_table in seed:
            keep.add(edge.to_table)
        if edge.to_table in seed:
            keep.add(edge.from_table)
    return SchemaGraph(
        instance_id=graph.instance_id,
        area_key=graph.area_key,
        discovered_at=graph.discovered_at,
        scope_keys=graph.scope_keys,
        tables=tuple(t for t in graph.tables if t.name in keep),
        reference_edges=tuple(
            e for e in graph.reference_edges if e.from_table in keep and e.to_table in keep
        ),
        inheritance_edges=tuple(
            e for e in graph.inheritance_edges if e.table in keep and e.extends in keep
        ),
        relationship_edges=tuple(
            e for e in graph.relationship_edges if e.apply_to in keep and e.query_from in keep
        ),
    )
