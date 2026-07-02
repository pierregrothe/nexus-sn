# scripts/spike_s0_closure_scale.py
# S0 spike: measure reference-field closure wall-clock, finding counts, and lane-unit count.
# Author: Pierre Grothe
# Date: 2026-07-02
"""Pure, offline closure-scale measurement harness (Story 00 of the migration-planner epic).

Loads the already-captured 30K-artifact inventory JSONs
(``artifacts/replatform-proof/inventory-{alectri,retail}-v2.json``) plus an
offline schema-graph archive (produced once by
``scripts/spike_s0_fetch_schema_edges.py``), and walks a structural
upper-bound reference-field closure over them: the inventories are
name-only, so per-artifact reference *values* are unknown -- for each
artifact, every reference edge declared on its table is a raw closure
*candidate*, not a confirmed dependency. The walk is timed with
``time.perf_counter()`` and run twice (empty stop-list vs. the seed
stop-list) to produce the four AC2 measurements: wall-clock, finding count
without a stop-list, finding count with the seed stop-list, and lane-unit
count.

PURE by construction: every load function reads plain JSON with the
standard library only. No ``nexus.*`` module is ever imported -- in
particular, importing any ``nexus.schema`` submodule transitively imports
``nexus.schema.engine`` (via that package's eager ``__init__.py``), which
imports ``httpx``/``nexus.connectors``/``nexus.api``. Rather than depend on
``nexus.schema.archive.SchemaArchiveReader`` and inherit that import graph,
this harness parses the archive's well-known JSON shape directly. AC5 is
enforced by ``_assert_no_network_client``, which asserts none of those
modules ever entered ``sys.modules``.

Usage (human-run; not part of the pytest suite -- see tests/spikes/):
    poetry run python scripts/spike_s0_closure_scale.py > s0-run.txt
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ClosureWalkResult",
    "LaneUnitCounts",
    "WorkflowEntry",
    "count_lane_units",
    "load_inventory_workflows",
    "load_schema_edges",
    "load_stop_list",
    "main",
    "walk_closure",
]

type ReferencePair = tuple[str, str]  # (field, to_table)
type EdgeMap = Mapping[str, tuple[ReferencePair, ...]]
type Finding = tuple[str, str, str, str]  # (use_case_key, from_table, field, to_table)

_DEFAULT_ALECTRI_INVENTORY = Path("artifacts/replatform-proof/inventory-alectri-v2.json")
_DEFAULT_RETAIL_INVENTORY = Path("artifacts/replatform-proof/inventory-retail-v2.json")
_DEFAULT_ARCHIVE_ROOT = Path("artifacts/replatform-proof")
_DEFAULT_STOP_LIST = Path(".primer/epics/2026.08-nexus-migration-planner/seed-stop-list.yaml")
_AREA_KEY = "s0-platform-artifacts"

# Custom-scoped-app prefix, matching nexus.cli.commands_assess_replatform._CUSTOM_PREFIXES.
_CUSTOM_SCOPE_PREFIXES = ("x_", "u_")

# AC5: modules that would signal a network client was constructed.
_NETWORK_MODULE_PREFIXES = ("nexus.connectors", "nexus.api")
_NETWORK_MODULE_NAMES = ("httpx",)


@dataclass(slots=True, frozen=True)
class WorkflowEntry:
    """One artifact row read from a UseCaseInventory-shaped JSON file.

    Args:
        use_case_key: Key of the owning use case.
        table: Source table name (artifact type, e.g. "sys_script").
        scope: Technical scope key the artifact belongs to (e.g. "global").
    """

    use_case_key: str
    table: str
    scope: str


@dataclass(slots=True, frozen=True)
class ClosureWalkResult:
    """Outcome of one closure walk over an inventory.

    Args:
        raw_expansion: Raw (artifact, edge) candidate pairs whose to_table
            is not on the stop-list.
        raw_data_prerequisite: Raw candidate pairs whose to_table is on the
            stop-list (dampened into a DATA_PREREQUISITE candidate).
        dedup_expansion: Deduplicated expansion findings, at
            (use_case, from_table, field, to_table) granularity.
        dedup_data_prerequisite: Deduplicated data-prerequisite findings, at
            the same granularity.
    """

    raw_expansion: int
    raw_data_prerequisite: int
    dedup_expansion: frozenset[Finding]
    dedup_data_prerequisite: frozenset[Finding]

    @property
    def raw_total(self) -> int:
        """Total raw candidate pairs across both buckets."""
        return self.raw_expansion + self.raw_data_prerequisite

    @property
    def dedup_total(self) -> int:
        """Total deduplicated findings across both buckets.

        The two buckets never overlap: a finding's to_table membership in
        the stop-list is fixed, so each finding tuple falls into exactly
        one bucket.
        """
        return len(self.dedup_expansion) + len(self.dedup_data_prerequisite)

    @property
    def stop_tables_hit(self) -> frozenset[str]:
        """Stop-list tables actually hit by at least one dampened finding."""
        return frozenset(finding[3] for finding in self.dedup_data_prerequisite)


@dataclass(slots=True, frozen=True)
class LaneUnitCounts:
    """Lane-unit count breakdown (Design Resolution 5).

    Args:
        scoped_apps: Distinct custom (x_/u_) scope keys -- APP_REPO lane
            units, one per scoped app.
        global_use_cases: Distinct use-case keys with at least one
            global-scope workflow -- UPDATE_SET-sized config groupings.
        data_batches: Distinct stop-list tables hit by at least one
            dampened edge -- one DATA lane bucket per table.
    """

    scoped_apps: int
    global_use_cases: int
    data_batches: int

    @property
    def total(self) -> int:
        """Sum of the three lane-unit addends."""
        return self.scoped_apps + self.global_use_cases + self.data_batches


def load_inventory_workflows(path: Path) -> tuple[WorkflowEntry, ...]:
    """Load workflow rows from a UseCaseInventory-shaped JSON file.

    Reads the file with plain ``json.loads`` rather than
    ``nexus.replatform.models.UseCaseInventory`` -- the harness never
    imports any ``nexus.*`` module (see module docstring).

    Args:
        path: Path to an ``inventory-<profile>-v2.json`` file.

    Returns:
        One WorkflowEntry per workflow, in file order.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries: list[WorkflowEntry] = []
    for use_case in raw.get("use_cases", []):
        uc_key = str(use_case["key"])
        for workflow in use_case.get("workflows", []):
            entries.append(
                WorkflowEntry(
                    use_case_key=uc_key,
                    table=str(workflow["type"]),
                    scope=str(workflow["scope"]),
                )
            )
    return tuple(entries)


def load_schema_edges(path: Path) -> EdgeMap:
    """Load reference edges from a SchemaGraph JSON archive as a plain dict.

    Args:
        path: Path to a schema archive JSON file written by
            ``SchemaArchiveWriter`` (see ``scripts/spike_s0_fetch_schema_edges.py``).

    Returns:
        Mapping of ``from_table`` to its ``(field, to_table)`` reference
        pairs.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    edges: dict[str, list[ReferencePair]] = {}
    for edge in raw.get("reference_edges", []):
        edges.setdefault(str(edge["from_table"]), []).append(
            (str(edge["field"]), str(edge["to_table"]))
        )
    return {table: tuple(pairs) for table, pairs in edges.items()}


def load_stop_list(path: Path) -> frozenset[str]:
    """Parse a flat stop-list YAML (``- table_name`` lines) into a set.

    A hand-rolled parser is used instead of a YAML library dependency: the
    file is a flat list with an ASCII comment header, which a two-line loop
    reads without pulling PyYAML into a spike script.

    Args:
        path: Path to the seed stop-list YAML.

    Returns:
        Frozenset of table names.
    """
    tables: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            tables.add(stripped.removeprefix("- ").strip())
    return frozenset(tables)


def walk_closure(
    workflows: Sequence[WorkflowEntry],
    edges_by_table: EdgeMap,
    stop_list: frozenset[str],
) -> ClosureWalkResult:
    """Structural upper-bound reference-field closure walk.

    For each artifact, every reference edge declared on its table is a raw
    closure candidate (the inventory is name-only, so whether that edge's
    field is actually populated on a given artifact is unknown -- this is
    an upper bound, not a confirmed dependency count). Candidates whose
    target table is on ``stop_list`` are dampened into data-prerequisite
    candidates instead of expansion candidates.

    Args:
        workflows: Artifacts to walk (one inventory's worth).
        edges_by_table: Reference edges keyed by source table.
        stop_list: Table names that dampen expansion into DATA_PREREQUISITE.

    Returns:
        The raw and deduplicated candidate counts, split by bucket.
    """
    raw_expansion = 0
    raw_data_prerequisite = 0
    dedup_expansion: set[Finding] = set()
    dedup_data_prerequisite: set[Finding] = set()
    for workflow in workflows:
        for field, to_table in edges_by_table.get(workflow.table, ()):
            finding = (workflow.use_case_key, workflow.table, field, to_table)
            if to_table in stop_list:
                raw_data_prerequisite += 1
                dedup_data_prerequisite.add(finding)
            else:
                raw_expansion += 1
                dedup_expansion.add(finding)
    return ClosureWalkResult(
        raw_expansion=raw_expansion,
        raw_data_prerequisite=raw_data_prerequisite,
        dedup_expansion=frozenset(dedup_expansion),
        dedup_data_prerequisite=frozenset(dedup_data_prerequisite),
    )


def count_lane_units(
    workflows: Sequence[WorkflowEntry], stop_tables_hit: frozenset[str]
) -> LaneUnitCounts:
    """Count lane units per Design Resolution 5.

    Args:
        workflows: The inventory's artifacts (one instance's worth).
        stop_tables_hit: Stop-list tables actually hit by a dampened edge
            (``ClosureWalkResult.stop_tables_hit`` from the seeded walk).

    Returns:
        The three lane-unit addends (scoped apps, global use cases, data
        batches).
    """
    scoped_apps = {wf.scope for wf in workflows if wf.scope.startswith(_CUSTOM_SCOPE_PREFIXES)}
    global_use_cases = {wf.use_case_key for wf in workflows if wf.scope == "global"}
    return LaneUnitCounts(
        scoped_apps=len(scoped_apps),
        global_use_cases=len(global_use_cases),
        data_batches=len(stop_tables_hit),
    )


def _find_latest_archive(root: Path, instance: str) -> Path | None:
    """Find the most recently written schema archive for one instance.

    Archive filenames are ``{area_key}-{YYYYmmdd-HHMMSS}.json``, so
    lexicographic order matches chronological order.

    Args:
        root: Archive root directory (e.g. artifacts/replatform-proof).
        instance: Instance profile subdirectory to search.

    Returns:
        The latest matching archive path, or None if none exist.
    """
    candidates = sorted((root / instance).glob(f"{_AREA_KEY}-*.json"))
    return candidates[-1] if candidates else None


# The sys.modules default is intentional: checked by reference at call time,
# never copied -- do not "fix" by snapshotting (dict(sys.modules)) at import.
def _assert_no_network_client(modules: Mapping[str, object] = sys.modules) -> str:
    """Enforce AC5: this process must never have loaded a client-carrying module.

    ``modules`` defaults to the live ``sys.modules`` (the real check main()
    runs); tests inject a synthetic mapping so the pass/fail branches are
    exercisable without depending on whether some unrelated import in the
    test process happened to pull in httpx.

    Args:
        modules: Mapping of loaded module names to module objects.

    Returns:
        A human-readable pass line for the printed report.

    Raises:
        AssertionError: If httpx or any nexus.connectors/nexus.api module
            name is present in ``modules``.
    """
    leaked = sorted(
        name
        for name in modules
        if name in _NETWORK_MODULE_NAMES or name.startswith(_NETWORK_MODULE_PREFIXES)
    )
    assert not leaked, f"AC5 VIOLATION: network-capable modules loaded: {leaked}"
    return "AC5 guard: PASS -- no httpx/nexus.connectors/nexus.api module in sys.modules"


def main() -> int:
    """Run the S0 closure-scale measurement and print the AC2 numbers.

    Returns:
        Process exit code (0 on success, 1 if no schema archive is found).
    """
    schema_archive = _find_latest_archive(_DEFAULT_ARCHIVE_ROOT, "alectri")
    if schema_archive is None:
        print(
            "No schema archive found under artifacts/replatform-proof/alectri/ -- "
            "run scripts/spike_s0_fetch_schema_edges.py first.",
            file=sys.stderr,
        )
        return 1

    stop_list = load_stop_list(_DEFAULT_STOP_LIST)

    t0 = time.perf_counter()
    alectri_workflows = load_inventory_workflows(_DEFAULT_ALECTRI_INVENTORY)
    retail_workflows = load_inventory_workflows(_DEFAULT_RETAIL_INVENTORY)
    edges = load_schema_edges(schema_archive)
    load_elapsed = time.perf_counter() - t0
    total_edges = sum(len(pairs) for pairs in edges.values())
    print(
        f"JSON load: {load_elapsed:.3f}s -- alectri={len(alectri_workflows)} artifacts, "
        f"retail={len(retail_workflows)} artifacts, "
        f"{total_edges} reference edges across {len(edges)} tables (archive={schema_archive})"
    )

    t1 = time.perf_counter()
    empty_result = walk_closure(alectri_workflows, edges, frozenset())
    empty_elapsed = time.perf_counter() - t1
    print(
        f"alectri walk, empty stop-list: {empty_elapsed * 1000:.2f}ms -- "
        f"raw={empty_result.raw_total} deduped={empty_result.dedup_total}"
    )

    t2 = time.perf_counter()
    seeded_result = walk_closure(alectri_workflows, edges, stop_list)
    seeded_elapsed = time.perf_counter() - t2
    print(
        f"alectri walk, seed stop-list {sorted(stop_list)}: {seeded_elapsed * 1000:.2f}ms -- "
        f"raw_expansion={seeded_result.raw_expansion} "
        f"raw_data_prerequisite={seeded_result.raw_data_prerequisite} "
        f"dedup_expansion={len(seeded_result.dedup_expansion)} "
        f"dedup_data_prerequisite={len(seeded_result.dedup_data_prerequisite)} "
        f"dedup_total={seeded_result.dedup_total}"
    )
    print(f"S0 wall-clock (headline, seed-stop-list walk): {seeded_elapsed * 1000:.2f}ms")

    t3 = time.perf_counter()
    retail_result = walk_closure(retail_workflows, edges, stop_list)
    retail_elapsed = time.perf_counter() - t3
    print(
        f"retail walk, seed stop-list (confirmation run): {retail_elapsed * 1000:.2f}ms -- "
        f"raw={retail_result.raw_total} deduped={retail_result.dedup_total}"
    )

    lanes = count_lane_units(alectri_workflows, seeded_result.stop_tables_hit)
    print(
        f"Lane units (alectri): scoped_apps={lanes.scoped_apps} "
        f"global_use_cases={lanes.global_use_cases} data_batches={lanes.data_batches} "
        f"total={lanes.total}"
    )

    print(_assert_no_network_client())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
