# src/nexus/migrate/__init__.py
# Selective-migration planner: plan-file models and byte-stable YAML round trip.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Selective-migration planner for ServiceNow instance-to-instance migration.

Frozen plan-file models (Selection -> MigrationPlan) and the byte-stable YAML
emit/load pair that makes the plan file the auditable artifact of record
(ADR-026 Decision 2), plus the selection-to-capture bridge that turns a
curated Selection into full CaptureResult(s) for closure to walk (Story 01).
Advisory only: this layer never mutates an instance.
"""

from nexus.migrate.capture_bridge import build_capture_for_selection
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
    load_plan_yaml,
)

__all__ = [
    "Acknowledgment",
    "FindingKind",
    "IntegrityFinding",
    "MigrationPlan",
    "PlanItem",
    "PlanLane",
    "Selection",
    "SelectionItem",
    "Waiver",
    "Wave",
    "build_capture_for_selection",
    "emit_plan_yaml",
    "load_plan_yaml",
]
