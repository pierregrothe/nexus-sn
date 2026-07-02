# src/nexus/migrate/__init__.py
# Selective-migration planner: plan-file models and byte-stable YAML round trip.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Selective-migration planner for ServiceNow instance-to-instance migration.

Frozen plan-file models (Selection -> MigrationPlan) and the byte-stable YAML
emit/load pair that makes the plan file the auditable artifact of record
(ADR-026 Decision 2), the selection-to-capture bridge that turns a curated
Selection into full CaptureResult(s) (Story 01), the pure closure/wave
builder that expands a Selection into its dependency closure and orders it
into topologically-sorted waves (Story 04), and the pure drift-detection
core `plan --recheck` diffs a plan's baselines against a fresh re-inventory
with (Story 06). Advisory only: this layer never mutates an instance.
"""

from nexus.migrate.capture_bridge import (
    build_capture_for_selection,
    field_display,
    natural_key_segment,
    record_natural_key,
)
from nexus.migrate.closure import (
    DEFAULT_STOP_LIST,
    ClosureItem,
    ClosureResult,
    OrderingEdge,
    build_closure,
    load_stop_list,
)
from nexus.migrate.models import (
    Acknowledgment,
    BaselineEntry,
    DriftReport,
    FindingKind,
    IntegrityFinding,
    MigrationPlan,
    PlanItem,
    PlanLane,
    Selection,
    SelectionItem,
    Waiver,
    Wave,
    emit_plan_yaml,
    emit_selection_yaml,
    load_plan_yaml,
    load_selection_yaml,
)
from nexus.migrate.planner import build_waves, detect_cycles, validate_approval
from nexus.migrate.recheck import compute_drift, listing_from_entries, plan_has_baseline

__all__ = [
    "DEFAULT_STOP_LIST",
    "Acknowledgment",
    "BaselineEntry",
    "ClosureItem",
    "ClosureResult",
    "DriftReport",
    "FindingKind",
    "IntegrityFinding",
    "MigrationPlan",
    "OrderingEdge",
    "PlanItem",
    "PlanLane",
    "Selection",
    "SelectionItem",
    "Waiver",
    "Wave",
    "build_capture_for_selection",
    "build_closure",
    "build_waves",
    "compute_drift",
    "detect_cycles",
    "emit_plan_yaml",
    "emit_selection_yaml",
    "field_display",
    "listing_from_entries",
    "load_plan_yaml",
    "load_selection_yaml",
    "load_stop_list",
    "natural_key_segment",
    "plan_has_baseline",
    "record_natural_key",
    "validate_approval",
]
