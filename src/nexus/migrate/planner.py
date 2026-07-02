# src/nexus/migrate/planner.py
# Pure wave builder + approval-blocking validator (story 04b).
# Author: Pierre Grothe
# Date: 2026-07-02

"""Order closure items into topologically-sorted waves and gate approval.

``build_waves`` assigns each ``ClosureItem`` the smallest wave index
consistent with ``OrderingEdge`` dependencies (AC6): wave index 0 when an
item has no dependencies, else ``1 + max(wave index of its dependencies)``.
Dependency cycles do not raise and are not silently broken -- cycle members
are placed together in one wave (AC7); ``detect_cycles`` is the sibling
function that surfaces the CYCLE finding for that placement (kept separate
from ``build_waves`` so its return type matches AC6's literal pinned
signature, ``build_waves(items, edges) -> tuple[Wave, ...]``, exactly).

``validate_approval`` returns blocking reasons for an assembled
``MigrationPlan`` (AC8-AC10). Both functions are pure: no ServiceNow calls,
no I/O.

Determinism (load-bearing): SCC membership and condensation-graph layering
are graph-topological properties independent of input ordering, so
``build_waves``/``detect_cycles`` are order-independent by construction.
Wave membership is additionally sorted lexicographically by item key within
each wave before being returned.
"""

import logging
from dataclasses import dataclass

from nexus.migrate.closure import ClosureItem, OrderingEdge
from nexus.migrate.models import FindingKind, IntegrityFinding, MigrationPlan, PlanItem, Wave

log = logging.getLogger(__name__)

__all__ = ["build_waves", "detect_cycles", "validate_approval"]


def _tarjan_sccs(nodes: list[str], adjacency: dict[str, frozenset[str]]) -> list[list[str]]:
    """Find strongly-connected components via iterative Tarjan's algorithm.

    Iterative (not recursive) to avoid Python's recursion-depth ceiling on
    large dependency chains.

    Args:
        nodes: All node keys, visited in this order for deterministic SCC
            discovery (SCC *membership* is order-independent regardless).
        adjacency: node -> set of nodes it has an outbound edge to.

    Returns:
        The graph's SCCs, each as a list of member keys (component-discovery
        order, not otherwise meaningful -- callers sort as needed).
    """
    index_of: dict[str, int] = {}
    low_link: dict[str, int] = {}
    on_stack: set[str] = set()
    tarjan_stack: list[str] = []
    sccs: list[list[str]] = []
    counter = 0

    for root in nodes:
        if root in index_of:
            continue
        index_of[root] = counter
        low_link[root] = counter
        counter += 1
        tarjan_stack.append(root)
        on_stack.add(root)
        # Explicit work stack of (node, sorted neighbors, next-neighbor index)
        # simulates the recursive DFS call stack.
        work: list[tuple[str, list[str], int]] = [(root, sorted(adjacency.get(root, ())), 0)]

        while work:
            node, neighbors, pos = work[-1]
            if pos < len(neighbors):
                work[-1] = (node, neighbors, pos + 1)
                neighbor = neighbors[pos]
                if neighbor not in index_of:
                    index_of[neighbor] = counter
                    low_link[neighbor] = counter
                    counter += 1
                    tarjan_stack.append(neighbor)
                    on_stack.add(neighbor)
                    work.append((neighbor, sorted(adjacency.get(neighbor, ())), 0))
                elif neighbor in on_stack:
                    low_link[node] = min(low_link[node], index_of[neighbor])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low_link[parent] = min(low_link[parent], low_link[node])
                if low_link[node] == index_of[node]:
                    component: list[str] = []
                    while True:
                        member = tarjan_stack.pop()
                        on_stack.discard(member)
                        component.append(member)
                        if member == node:
                            break
                    sccs.append(component)

    return sccs


def _layer_condensation(scc_ids: list[int], scc_deps: dict[int, set[int]]) -> dict[int, int]:
    """Assign each SCC the smallest layer consistent with its condensation deps.

    The condensation graph (SCCs as nodes, edges collapsed across members) is
    always acyclic, so Kahn peeling always drains ``remaining`` completely.

    Args:
        scc_ids: All SCC ids.
        scc_deps: SCC id -> set of SCC ids it depends on (excludes self).

    Returns:
        SCC id -> layer (0-based, dense, no gaps).
    """
    dependents: dict[int, set[int]] = {scc_id: set() for scc_id in scc_ids}
    remaining_deps: dict[int, set[int]] = {
        scc_id: set(scc_deps.get(scc_id, ())) for scc_id in scc_ids
    }
    for scc_id, deps in remaining_deps.items():
        for dep in deps:
            dependents[dep].add(scc_id)

    layer: dict[int, int] = {}
    remaining = set(scc_ids)
    round_num = 0
    frontier = sorted(scc_id for scc_id in remaining if not remaining_deps[scc_id])
    while frontier:
        for scc_id in frontier:
            layer[scc_id] = round_num
        remaining -= set(frontier)
        for scc_id in frontier:
            for dependent in dependents[scc_id]:
                remaining_deps[dependent].discard(scc_id)
        frontier = sorted(scc_id for scc_id in remaining if not remaining_deps[scc_id])
        round_num += 1

    return layer


@dataclass(slots=True, frozen=True)
class _Layout:
    """Shared computation behind build_waves/detect_cycles.

    Avoids duplicating the SCC + condensation-layering pass across the two
    public functions.
    """

    wave_index: dict[str, int]
    cycle_findings: tuple[IntegrityFinding, ...]


def _compute_layout(items: tuple[ClosureItem, ...], edges: tuple[OrderingEdge, ...]) -> _Layout:
    """Compute each item's wave_index and one CYCLE finding per non-trivial SCC."""
    keys = sorted(item.key for item in items)
    key_set = set(keys)
    adjacency: dict[str, set[str]] = {key: set() for key in keys}
    for edge in edges:
        if edge.dependent_key not in key_set or edge.dependency_key not in key_set:
            continue
        if edge.dependent_key == edge.dependency_key:
            # A self-loop is its own trivial cycle; skip it as an ordering
            # edge (a node can't be placed strictly after itself) but treat
            # it as a cycle for finding/placement purposes below.
            continue
        adjacency[edge.dependent_key].add(edge.dependency_key)

    frozen_adjacency = {key: frozenset(deps) for key, deps in adjacency.items()}
    sccs = _tarjan_sccs(keys, frozen_adjacency)

    scc_of: dict[str, int] = {}
    for scc_id, members in enumerate(sccs):
        for member in members:
            scc_of[member] = scc_id

    scc_deps: dict[int, set[int]] = {scc_id: set() for scc_id in range(len(sccs))}
    for key, deps in adjacency.items():
        for dep in deps:
            if scc_of[dep] != scc_of[key]:
                scc_deps[scc_of[key]].add(scc_of[dep])

    layer = _layer_condensation(list(range(len(sccs))), scc_deps)

    self_loop_keys = {
        edge.dependent_key for edge in edges if edge.dependent_key == edge.dependency_key
    }
    wave_index: dict[str, int] = {}
    cycle_findings: list[IntegrityFinding] = []
    for scc_id, members in enumerate(sccs):
        for member in members:
            wave_index[member] = layer[scc_id]
        is_cycle = len(members) > 1 or (len(members) == 1 and members[0] in self_loop_keys)
        if is_cycle:
            sorted_members = sorted(members)
            cycle_findings.append(
                IntegrityFinding(
                    kind=FindingKind.CYCLE,
                    subject_key=sorted_members[0],
                    detail=f"dependency cycle among: {', '.join(sorted_members)}",
                )
            )

    return _Layout(
        wave_index=wave_index,
        cycle_findings=tuple(
            sorted(cycle_findings, key=lambda f: (f.kind, f.subject_key, f.detail))
        ),
    )


def build_waves(
    items: tuple[ClosureItem, ...], edges: tuple[OrderingEdge, ...]
) -> tuple[Wave, ...]:
    """Order closure items into topologically-sorted waves (AC6, AC7).

    Every item's wave index is strictly greater than every item it depends
    on's wave index; items sharing no ordering constraint share the earliest
    possible wave. Dependency cycles do not raise -- their members are
    placed together in a single wave positioned after their non-cycle
    dependencies (AC7); call ``detect_cycles`` with the same arguments to get
    the CYCLE finding for that placement.

    Args:
        items: Closure items to place into waves.
        edges: Wave-ordering constraints between item keys.

    Returns:
        Waves in ascending index order; within each wave, items are sorted
        lexicographically by key.
    """
    layout = _compute_layout(items, edges)
    item_by_key = {item.key: item for item in items}

    waves_by_index: dict[int, list[PlanItem]] = {}
    for key in sorted(item_by_key):
        source = item_by_key[key]
        plan_item = PlanItem(
            key=source.key,
            lane=source.lane,
            added_by_closure=source.added_by_closure,
            wave_index=layout.wave_index[key],
        )
        waves_by_index.setdefault(plan_item.wave_index, []).append(plan_item)

    return tuple(
        Wave(index=index, items=tuple(sorted(waves_by_index[index], key=lambda pi: pi.key)))
        for index in sorted(waves_by_index)
    )


def detect_cycles(
    items: tuple[ClosureItem, ...], edges: tuple[OrderingEdge, ...]
) -> tuple[IntegrityFinding, ...]:
    """Detect dependency cycles among closure items, one CYCLE finding per cycle.

    Companion to ``build_waves`` (same arguments, same underlying SCC
    computation) -- call both and merge ``detect_cycles``'s findings into
    ``MigrationPlan.findings`` alongside ``build_closure``'s findings.

    Args:
        items: Closure items being placed into waves.
        edges: Wave-ordering constraints between item keys.

    Returns:
        One CYCLE finding per strongly-connected component of size > 1 (or a
        self-referencing item), sorted by (kind, subject_key, detail), naming
        every member of the cycle in its detail text.
    """
    return _compute_layout(items, edges).cycle_findings


def validate_approval(plan: MigrationPlan) -> tuple[str, ...]:
    """Return blocking reasons preventing ``plan`` from being approved (AC8-AC10).

    v1 blocks on exactly two finding kinds:

    * ``STRANDED_DEPENDENCY`` without a ``waiver`` attached.
    * ``DATA_PREREQUISITE`` without an ``acknowledgment`` attached.

    ``CYCLE`` and ``ACCESS_POSTURE_DRIFT`` findings are surfaced in the plan
    but are deliberately NON-BLOCKING in v1 -- this is an extension point: a
    later story may promote either to blocking once runbook guidance exists
    for resolving them (cycles need a manual sequencing decision;
    access-posture drift needs a security review step neither of which this
    story defines).

    Args:
        plan: The assembled MigrationPlan to validate.

    Returns:
        A blocking reason per unwaived/unacknowledged finding, naming the
        finding's kind and subject_key. Empty when nothing blocks approval.
    """
    reasons: list[str] = []
    for finding in plan.findings:
        match finding.kind:
            case FindingKind.STRANDED_DEPENDENCY:
                if finding.waiver is None:
                    reasons.append(
                        f"{finding.kind.value} on {finding.subject_key!r} is unwaived: "
                        f"{finding.detail}"
                    )
            case FindingKind.DATA_PREREQUISITE:
                if finding.acknowledgment is None:
                    reasons.append(
                        f"{finding.kind.value} on {finding.subject_key!r} is unacknowledged: "
                        f"{finding.detail}"
                    )
            case FindingKind.CYCLE | FindingKind.ACCESS_POSTURE_DRIFT:
                pass
            case _:  # pragma: no cover -- FindingKind is closed to 4 members; unreachable today.
                pass
    return tuple(reasons)
