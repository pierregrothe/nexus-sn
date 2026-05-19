# src/nexus/assessment/context.py
# GateContext + ApplyResult.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Uniform context object handed to every Gate.evaluate call.

GateContext bundles the CaptureResult, an optional ApplyResult (set for
Gate 2 / post-apply contexts only), and the Phase the calling gate is
evaluating.

ApplyResult is the structured outcome of `ApplyEngine.apply(template)`,
populated by the Template Library epic.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from nexus.assessment.schemas.enums import Phase
from nexus.capture.models import CaptureResult
from nexus.config.types import UtcDatetime
from nexus.templates.results import AppliedRecord

__all__ = ["ApplyResult", "GateContext"]


class ApplyResult(BaseModel):
    """Structured outcome of one `ApplyEngine.apply` call.

    Attributes:
        update_set_sys_id: sys_id of the sys_update_set that received the
            rendered records.
        update_set_name: Display name of the update set (carries the
            NEXUS-apply-<template>-<ts> provenance marker).
        template_id: Identifier of the applied template.
        template_version: Version of the applied template.
        target_scope_sys_id: Resolved scope sys_id the apply targeted.
        applied_records: Per-record outcome tuple recording what was
            requested (and any failures observed).
        instance_id: Profile name of the ServiceNow instance.
        started_at: Apply start timestamp.
        completed_at: Apply completion timestamp.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    update_set_sys_id: str = Field(..., min_length=1)
    update_set_name: str = Field(..., min_length=1)
    template_id: str = Field(..., min_length=1)
    template_version: str = Field(..., min_length=1)
    target_scope_sys_id: str = Field(..., min_length=1)
    applied_records: tuple[AppliedRecord, ...] = ()
    instance_id: str = Field(..., min_length=1)
    started_at: UtcDatetime
    completed_at: UtcDatetime


class GateContext(BaseModel):
    """Input shared by Gate1Readiness, Gate2Validation, HealthScan.

    Attributes:
        capture: The CaptureResult under evaluation.
        apply_result: For POST_APPLY (Gate 2). None for PRE_APPLY/STANDALONE.
        phase: The phase the calling gate is evaluating.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    capture: CaptureResult
    apply_result: ApplyResult | None
    phase: Phase
