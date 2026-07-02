# tests/fakes/migrate.py
# Builders for migrate plan-file model test fixtures.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Factory helpers for nexus.migrate tests.

Build real Selection, MigrationPlan, Waiver, and Acknowledgment instances
(and their nested models) with realistic natural keys and profile names, so
Stories 03-07 can reuse them without re-implementing the closure/plan-builder
layers those stories add. No mocks: every builder returns a real, frozen
Pydantic model.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

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
)

__all__ = [
    "make_acknowledgment",
    "make_integrity_finding",
    "make_migration_plan",
    "make_plan_item",
    "make_selection",
    "make_selection_item",
    "make_waiver",
    "make_wave",
]

_DEFAULT_TS = datetime(2026, 7, 2, 12, 0, 0, tzinfo=UTC)


def make_selection_item(
    *,
    key: str = "x_alectri_core|sys_hub_flow|approve po",
    disposition: Literal["include", "exclude", "undecided"] = "include",
    annotation: str = "",
    annotated_by: str = "",
) -> SelectionItem:
    """Build a SelectionItem with a realistic ``scope|table|name`` natural key."""
    return SelectionItem(
        key=key,
        disposition=disposition,
        annotation=annotation,
        annotated_by=annotated_by,
    )


def make_selection(
    *,
    source_profile: str = "alectri",
    target_profile: str = "retail",
    source_captured_at: datetime = _DEFAULT_TS,
    items: tuple[SelectionItem, ...] | None = None,
) -> Selection:
    """Build a Selection with one default curated item when none are supplied."""
    rows = items if items is not None else (make_selection_item(),)
    return Selection(
        source_profile=source_profile,
        target_profile=target_profile,
        source_captured_at=source_captured_at,
        items=rows,
    )


def make_plan_item(
    *,
    key: str = "x_alectri_core|sys_hub_flow|approve po",
    lane: PlanLane = PlanLane.UPDATE_SET,
    added_by_closure: bool = False,
    wave_index: int = 0,
) -> PlanItem:
    """Build a PlanItem with a realistic natural key and routing lane."""
    return PlanItem(key=key, lane=lane, added_by_closure=added_by_closure, wave_index=wave_index)


def make_wave(
    *,
    index: int = 0,
    items: tuple[PlanItem, ...] | None = None,
) -> Wave:
    """Build a Wave with one default PlanItem when none are supplied."""
    rows = items if items is not None else (make_plan_item(wave_index=index),)
    return Wave(index=index, items=rows)


def make_waiver(
    *,
    author: str = "alice",
    approver: str = "bob",
    reason: str = "dependency confirmed as a manual post-migration step",
    date: datetime = _DEFAULT_TS,
) -> Waiver:
    """Build a Waiver with distinct author/approver (passes segregation of duties)."""
    return Waiver(author=author, approver=approver, reason=reason, date=date)


def make_acknowledgment(
    *,
    author: str = "bob",
    reason: str = "data prerequisite seeded out of band before commit",
    date: datetime = _DEFAULT_TS,
) -> Acknowledgment:
    """Build an Acknowledgment for a non-blocking finding."""
    return Acknowledgment(author=author, reason=reason, date=date)


def make_integrity_finding(
    *,
    kind: FindingKind = FindingKind.STRANDED_DEPENDENCY,
    subject_key: str = "x_alectri_core|sys_hub_flow|approve po",
    detail: str = "references x_alectri_core|sys_db_object|po_request, which is excluded",
    waiver: Waiver | None = None,
    acknowledgment: Acknowledgment | None = None,
) -> IntegrityFinding:
    """Build an IntegrityFinding, optionally cleared by a waiver or acknowledgment."""
    return IntegrityFinding(
        kind=kind,
        subject_key=subject_key,
        detail=detail,
        waiver=waiver,
        acknowledgment=acknowledgment,
    )


def make_migration_plan(
    *,
    schema_version: str = "1.0",
    source_profile: str = "alectri",
    target_profile: str = "retail",
    source_captured_at: datetime = _DEFAULT_TS,
    target_captured_at: datetime = _DEFAULT_TS,
    waves: tuple[Wave, ...] | None = None,
    findings: tuple[IntegrityFinding, ...] | None = None,
    approved_by: str = "",
    approved_at: datetime | None = None,
    target_chain: tuple[str, ...] = (),
) -> MigrationPlan:
    """Build a MigrationPlan with a default waived and a default acknowledged finding."""
    plan_waves = waves if waves is not None else (make_wave(),)
    plan_findings = (
        findings
        if findings is not None
        else (
            make_integrity_finding(waiver=make_waiver()),
            make_integrity_finding(
                kind=FindingKind.DATA_PREREQUISITE,
                subject_key="x_alectri_core|sys_db_object|po_request",
                detail="table data must be seeded before update set commit",
                acknowledgment=make_acknowledgment(),
            ),
        )
    )
    return MigrationPlan(
        schema_version=schema_version,
        source_profile=source_profile,
        target_profile=target_profile,
        source_captured_at=source_captured_at,
        target_captured_at=target_captured_at,
        waves=plan_waves,
        findings=plan_findings,
        approved_by=approved_by,
        approved_at=approved_at,
        target_chain=target_chain,
    )
