# src/nexus/migrate/__init__.py
# Selective-migration planner: plan-file models and byte-stable YAML round trip.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Selective-migration planner for ServiceNow instance-to-instance migration.

Frozen plan-file models (Selection -> MigrationPlan) and the byte-stable YAML
emit/load pair that makes the plan file the auditable artifact of record
(ADR-026 Decision 2), the selection-to-capture bridge that turns a curated
Selection into full CaptureResult(s) (Story 01), and the pure closure
builder that expands a Selection into its dependency closure (Story 04a).
Advisory only: this layer never mutates an instance.
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

__all__ = [
    "DEFAULT_STOP_LIST",
    "Acknowledgment",
    "ClosureItem",
    "ClosureResult",
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
    "emit_plan_yaml",
    "emit_selection_yaml",
    "field_display",
    "load_plan_yaml",
    "load_selection_yaml",
    "load_stop_list",
    "natural_key_segment",
    "record_natural_key",
]
