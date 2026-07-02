# src/nexus/migrate/closure.py
# Pure dependency-closure builder: Selection + captures -> plan items/edges/findings.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Expand a curated Selection into its structured dependency closure (Story 04).

``build_closure`` walks reference fields between already-captured
``ConfigRecord``s (never live ServiceNow calls -- pure functions over
``CaptureResult`` tuples + an offline ``SchemaGraph``) to decide, for every
included item's outbound references, whether the referenced target should be
auto-added to the plan, raise a ``STRANDED_DEPENDENCY`` finding, or be
dampened into a ``DATA_PREREQUISITE`` finding (AC1, AC5). Co-capture rules
(AC2) always add certain detail rows regardless of disposition/stop-list.
``sys_scope_privilege`` presence (AC3) and ``sys_db_object`` access-posture
drift (AC4) are additional checks layered onto the same walk.

Recon decision (this epic, 2026-07-02): the three ``SelectionItem``
dispositions are asymmetric -- ``include`` is always in the plan;
``undecided`` MAY be auto-added (``added_by_closure=True``); ``exclude`` is
NEVER auto-added -- closure raises ``STRANDED_DEPENDENCY`` instead. Closure
must never silently override an explicit exclude.

Scope-key gap (documented, not fixed by this story): natural keys computed
here use ``record.scope_name`` as the scope segment (there is no live
scope-sys_id resolver available to a pure function). In production captures,
``ConfigFetcher`` populates ``scope_name`` from the raw ``sys_scope`` row
value, which may itself be a sys_id rather than the technical scope key --
that gap lives in ``nexus.capture.fetcher`` and is out of this story's
scope. This module's fixtures set ``scope_name`` to the correct technical
scope key directly, matching how ``Selection`` keys are built; Story 05's
live wiring must verify the production value lines up before calling this
module against real captures.

Determinism (load-bearing -- plans must be byte-stable): closure additions
are processed in sorted-key order, and the returned ``items``/``edges``/
``findings`` are each sorted before being returned, so the result never
depends on input record order (see
``tests/test_migrate_closure.py::test_build_closure_is_order_independent``).
"""

import logging
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

from nexus.capture.models import CaptureResult, ConfigRecord, SnFieldValue
from nexus.capture.tables import DEFAULT_TABLE_GROUPS
from nexus.migrate.capture_bridge import field_display, record_natural_key
from nexus.migrate.models import FindingKind, IntegrityFinding, PlanLane, Selection
from nexus.schema.models import ReferenceEdge, SchemaGraph

log = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_STOP_LIST",
    "ClosureItem",
    "ClosureResult",
    "OrderingEdge",
    "build_closure",
    "load_stop_list",
]

# Core-table stop-list default (Story 00 S0 closure-scale spike; provenance:
# .primer/epics/2026.08-nexus-migration-planner/seed-stop-list.yaml). Matching
# is EXACT table-name in v1 -- cmdb_ci child tables (cmdb_ci_server etc.) do
# NOT dampen under "cmdb_ci"; this is a known v1 gap tracked in the
# documented-gap register (Story 05's runbook), not implemented here.
DEFAULT_STOP_LIST: tuple[str, ...] = ("cmdb_ci", "sys_choice", "sys_user", "sys_user_group")

# AC3: sys_scope_privilege presence check. Field names are a sensible
# ServiceNow-shaped placeholder -- live verification is deferred to Story 05
# wiring; fixtures define the contract for this story.
_SCOPE_PRIV_TABLE = "sys_scope_privilege"
_SCOPE_PRIV_GRANTEE_FIELD = "application"
_SCOPE_PRIV_TARGET_FIELD = "target"

# AC4: sys_db_object access-posture diff. Field names are the story's named
# fields exactly ("accessible_from"/"caller_access"); "name" for the table
# identifier follows the real ServiceNow sys_db_object convention.
_SYS_DB_OBJECT_TABLE = "sys_db_object"
_SYS_DB_OBJECT_NAME_FIELD = "name"
_ACCESSIBLE_FROM_FIELD = "accessible_from"
_CALLER_ACCESS_FIELD = "caller_access"

# AC2 co-capture rules: table -> child-row specs that are ALWAYS added
# (added_by_closure=True), bypassing both disposition and the stop-list.
# Child rows are found by reference linkage in the captures (child.<link
# field> resolves to the parent's sys_id). Link field/table names are a
# sensible ServiceNow-shaped placeholder -- live verification of these exact
# names is deferred to Story 05 wiring; fixtures define the contract here.
_ACL_ROLE_TABLE = "sys_security_acl_role"
_ACL_ROLE_LINK_FIELD = "sys_security_acl"
_FLOW_SNAPSHOT_TABLE = "sys_hub_flow_snapshot"
_FLOW_SUBFLOW_TABLE = "sys_hub_flow_subflow"
_FLOW_ACTION_TABLE = "sys_hub_flow_action_instance"
_FLOW_CHILD_LINK_FIELD = "flow"

# Table -> display-name field, for computing natural keys of ANY captured
# table (not just the curatable tables offered by Story 03's checklist).
# Seeded from the capture-layer's own TableSpec registry (parity with
# capture_bridge's key computation); anything unregistered falls back to the
# ServiceNow convention of a plain "name" field.
_TABLE_NAME_FIELDS: dict[str, str] = {
    spec.name: spec.name_field for group in DEFAULT_TABLE_GROUPS.values() for spec in group.tables
}
_DEFAULT_NAME_FIELD = "name"


@dataclass(slots=True, frozen=True)
class _CoCaptureSpec:
    """One AC2 co-capture linkage rule.

    Attributes:
        child_table: Table holding the always-added detail rows.
        link_field: Field on ``child_table`` referencing the parent's sys_id.
    """

    child_table: str
    link_field: str


_CO_CAPTURE_RULES: dict[str, tuple[_CoCaptureSpec, ...]] = {
    "sys_security_acl": (_CoCaptureSpec(_ACL_ROLE_TABLE, _ACL_ROLE_LINK_FIELD),),
    "sys_hub_flow": (
        _CoCaptureSpec(_FLOW_SNAPSHOT_TABLE, _FLOW_CHILD_LINK_FIELD),
        _CoCaptureSpec(_FLOW_SUBFLOW_TABLE, _FLOW_CHILD_LINK_FIELD),
        _CoCaptureSpec(_FLOW_ACTION_TABLE, _FLOW_CHILD_LINK_FIELD),
    ),
}


@dataclass(slots=True, frozen=True)
class ClosureItem:
    """One item closure decided belongs in the plan, before wave placement.

    ``planner.build_waves`` consumes these to produce real ``PlanItem``s with
    an assigned ``wave_index``.

    Attributes:
        key: Natural key matching a SelectionItem or an item closure added.
        lane: Provisional routing hint (ADR-026 Decision 5); this story only
            ever sets the advisory default -- binding lane assignment is
            ADR-027 territory.
        added_by_closure: True when dependency closure pulled this item in
            rather than explicit curation.
    """

    key: str
    lane: PlanLane = PlanLane.UPDATE_SET
    added_by_closure: bool = False


@dataclass(slots=True, frozen=True)
class OrderingEdge:
    """A wave-ordering constraint (AC6).

    ``dependent_key`` must land in a strictly later wave than
    ``dependency_key``.

    Attributes:
        dependent_key: The referencing item's key.
        dependency_key: The referenced item's key.
    """

    dependent_key: str
    dependency_key: str


@dataclass(slots=True, frozen=True)
class ClosureResult:
    """Pure result of closing a Selection over its captured dependency graph.

    Attributes:
        items: Plan items to include, sorted by key.
        edges: Wave-ordering edges, sorted by (dependent_key, dependency_key).
        findings: Deduplicated integrity findings, sorted by
            (kind, subject_key, detail).
    """

    items: tuple[ClosureItem, ...]
    edges: tuple[OrderingEdge, ...]
    findings: tuple[IntegrityFinding, ...]


def load_stop_list(path: Path) -> tuple[str, ...]:
    """Load a custom core-table stop-list from a flat YAML list file.

    Matches Story 00's ``seed-stop-list.yaml`` shape: a flat YAML sequence of
    table names, with an arbitrary comment header (comments are not YAML
    data, so ``yaml.safe_load`` already ignores them).

    Args:
        path: Path to the stop-list YAML file.

    Returns:
        The table names, in file order.

    Raises:
        ValueError: When the file is not valid YAML or is not a flat list.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"stop-list YAML is not valid YAML: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError("stop-list YAML must be a flat list of table names")
    items = cast("list[object]", data)
    return tuple(str(item) for item in items)


def _name_field(table: str) -> str:
    """Return the display-name field for a table, defaulting to "name"."""
    return _TABLE_NAME_FIELDS.get(table, _DEFAULT_NAME_FIELD)


def _target_sys_id(value: SnFieldValue) -> str | None:
    """Extract a reference field's target sys_id, or None when it has no target.

    Args:
        value: A captured field value.

    Returns:
        The referenced sys_id for a non-empty SnRefField or plain non-empty
        string; None for missing/empty/non-reference values.
    """
    if isinstance(value, dict):
        sys_id = value["value"]
        return sys_id or None
    if isinstance(value, str) and value:
        return value
    return None


def _has_scope_grant(old_records: tuple[ConfigRecord, ...], grantee: str, target: str) -> bool:
    """Check the OLD capture for a sys_scope_privilege grant (AC3)."""
    for row in old_records:
        if row.table != _SCOPE_PRIV_TABLE:
            continue
        if field_display(row.fields.get(_SCOPE_PRIV_GRANTEE_FIELD)) != grantee:
            continue
        if field_display(row.fields.get(_SCOPE_PRIV_TARGET_FIELD)) != target:
            continue
        return True
    return False


def _find_db_object(records: tuple[ConfigRecord, ...], table: str) -> ConfigRecord | None:
    """Find the sys_db_object row describing ``table``, if captured."""
    for row in records:
        if row.table != _SYS_DB_OBJECT_TABLE:
            continue
        if field_display(row.fields.get(_SYS_DB_OBJECT_NAME_FIELD)) == table:
            return row
    return None


def _access_posture_findings(
    tables: Iterable[str],
    old_records: tuple[ConfigRecord, ...],
    new_records: tuple[ConfigRecord, ...],
) -> list[IntegrityFinding]:
    """Diff accessible_from/caller_access for each in-plan table (AC4)."""
    findings: list[IntegrityFinding] = []
    for table in sorted(set(tables)):
        old_row = _find_db_object(old_records, table)
        new_row = _find_db_object(new_records, table)
        if old_row is None or new_row is None:
            continue
        old_from = field_display(old_row.fields.get(_ACCESSIBLE_FROM_FIELD))
        new_from = field_display(new_row.fields.get(_ACCESSIBLE_FROM_FIELD))
        old_caller = field_display(old_row.fields.get(_CALLER_ACCESS_FIELD))
        new_caller = field_display(new_row.fields.get(_CALLER_ACCESS_FIELD))
        if old_from == new_from and old_caller == new_caller:
            continue
        findings.append(
            IntegrityFinding(
                kind=FindingKind.ACCESS_POSTURE_DRIFT,
                subject_key=table,
                detail=(
                    f"table {table!r} access posture drifted: "
                    f"accessible_from {old_from!r} -> {new_from!r}, "
                    f"caller_access {old_caller!r} -> {new_caller!r}"
                ),
            )
        )
    return findings


def build_closure(
    selection: Selection,
    captures: tuple[CaptureResult, ...],
    schema_graph: SchemaGraph,
    *,
    stop_list: tuple[str, ...] = DEFAULT_STOP_LIST,
) -> ClosureResult:
    """Close a curated Selection over its captured dependency graph (AC1-AC5).

    Pure function: no ServiceNow client, no I/O beyond the arguments given.
    ``captures`` may hold CaptureResults for both the source and target
    instance (``selection.source_profile``/``target_profile``); the
    reference-field walk, co-capture rules, and scope-privilege check (AC1-
    AC3) operate over the OLD (source) records only, while the access-
    posture diff (AC4) compares OLD against NEW.

    Args:
        selection: The curated Selection naming source-instance artifacts.
        captures: CaptureResult(s) covering the selection's artifacts (and,
            for AC4, the same tables captured from the target instance).
        schema_graph: Offline reference-edge graph used to resolve which
            fields on which tables carry cross-table references.
        stop_list: Core-table names that dampen reference-field closure into
            a DATA_PREREQUISITE finding instead of auto-adding the target
            row. Defaults to DEFAULT_STOP_LIST; pass ``load_stop_list(path)``
            for a custom list (AC5).

    Returns:
        A ClosureResult with deterministic, sorted items/edges/findings.
    """
    disposition_by_key: dict[str, Literal["include", "exclude", "undecided"]] = {
        item.key: item.disposition for item in selection.items
    }
    old_records = tuple(
        record
        for capture in captures
        if capture.instance_id == selection.source_profile
        for record in capture.records
    )
    new_records = tuple(
        record
        for capture in captures
        if capture.instance_id == selection.target_profile
        for record in capture.records
    )
    records_by_sys_id = {record.sys_id: record for record in old_records}
    records_by_key = {
        record_natural_key(record, _name_field(record.table), record.scope_name): record
        for record in old_records
    }

    edges_by_from_table: dict[str, list[ReferenceEdge]] = {}
    for edge in schema_graph.reference_edges:
        edges_by_from_table.setdefault(edge.from_table, []).append(edge)

    items: dict[str, ClosureItem] = {}
    ordering_edges: set[OrderingEdge] = set()
    findings: list[IntegrityFinding] = []

    seed_keys = sorted(
        key for key, disposition in disposition_by_key.items() if disposition == "include"
    )
    for key in seed_keys:
        items[key] = ClosureItem(key=key, added_by_closure=False)
    queue: deque[str] = deque(seed_keys)
    processed: set[str] = set()

    while queue:
        key = queue.popleft()
        if key in processed:
            # Defensive: every enqueue site (below) is guarded by "not in
            # items", and items are recorded synchronously with the enqueue,
            # so no key is ever queued twice by this algorithm today -- kept
            # as a guard against a future enqueue site dropping that check.
            continue  # pragma: no cover
        processed.add(key)
        record = records_by_key.get(key)
        if record is None:
            log.debug("closure: no captured record for selected key %r -- nothing to walk", key)
            continue

        for edge in edges_by_from_table.get(record.table, ()):
            target_sys_id = _target_sys_id(record.fields.get(edge.field))
            if target_sys_id is None:
                continue

            if edge.to_table in stop_list:
                findings.append(
                    IntegrityFinding(
                        kind=FindingKind.DATA_PREREQUISITE,
                        subject_key=key,
                        detail=(
                            f"references stop-listed core table {edge.to_table!r} "
                            f"via field {edge.field!r}"
                        ),
                    )
                )
                continue

            target_record = records_by_sys_id.get(target_sys_id)
            if target_record is None:
                # Unresolvable sys_id (not present in any provided capture):
                # no finding, no edge -- Story 05+ territory (cross-instance
                # or stale-reference resolution is not this story's job).
                continue

            target_key = record_natural_key(
                target_record, _name_field(target_record.table), target_record.scope_name
            )

            if target_record.scope_name != record.scope_name and not _has_scope_grant(
                old_records, record.scope_name, target_record.scope_name
            ):
                findings.append(
                    IntegrityFinding(
                        kind=FindingKind.STRANDED_DEPENDENCY,
                        subject_key=key,
                        detail=(
                            f"cross-scope reference from {record.scope_name!r} to "
                            f"{target_record.scope_name!r} lacks a sys_scope_privilege grant"
                        ),
                    )
                )

            match disposition_by_key.get(target_key):
                case "include":
                    ordering_edges.add(OrderingEdge(dependent_key=key, dependency_key=target_key))
                case "undecided":
                    ordering_edges.add(OrderingEdge(dependent_key=key, dependency_key=target_key))
                    if target_key not in items:
                        log.debug("closure: auto-adding undecided target %r", target_key)
                        items[target_key] = ClosureItem(key=target_key, added_by_closure=True)
                        queue.append(target_key)
                case "exclude":
                    findings.append(
                        IntegrityFinding(
                            kind=FindingKind.STRANDED_DEPENDENCY,
                            subject_key=key,
                            detail=f"references {target_key!r}, which is explicitly excluded",
                        )
                    )
                case None:
                    # Target isn't part of the curated Selection at all (not
                    # a stop-listed core table either) -- not covered by
                    # AC1's rule table; treated as a no-op, matching the
                    # "unresolvable reference" no-edge/no-finding rule above.
                    pass
                case _:  # pragma: no cover -- disposition is a closed Literal; unreachable.
                    pass

        for spec in _CO_CAPTURE_RULES.get(record.table, ()):
            for row in old_records:
                if row.table != spec.child_table:
                    continue
                if _target_sys_id(row.fields.get(spec.link_field)) != record.sys_id:
                    continue
                row_key = record_natural_key(row, _name_field(row.table), row.scope_name)
                ordering_edges.add(OrderingEdge(dependent_key=row_key, dependency_key=key))
                if row_key not in items:
                    items[row_key] = ClosureItem(key=row_key, added_by_closure=True)
                    queue.append(row_key)

    tables_in_plan = {key.split("|", 2)[1] for key in items}
    findings.extend(_access_posture_findings(tables_in_plan, old_records, new_records))

    sorted_items = tuple(items[key] for key in sorted(items))
    sorted_edges = tuple(sorted(ordering_edges, key=lambda e: (e.dependent_key, e.dependency_key)))
    sorted_findings = tuple(
        sorted(dict.fromkeys(findings), key=lambda f: (f.kind, f.subject_key, f.detail))
    )
    return ClosureResult(items=sorted_items, edges=sorted_edges, findings=sorted_findings)
