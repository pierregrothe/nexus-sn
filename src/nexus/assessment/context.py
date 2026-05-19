# src/nexus/assessment/context.py
# GateContext + ApplyResult placeholder.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Uniform context object handed to every Gate.evaluate call.

Story 03 introduces a minimal GateContext used by RuleEngine.evaluate.
Story 04 will not change the shape -- it adds GateProtocol/Gates that
consume this same context. ApplyResult is a placeholder Pydantic model
populated by the Template Library epic once ApplyEngine lands.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from nexus.assessment.schemas.enums import Phase
from nexus.capture.models import CaptureResult

__all__ = ["ApplyResult", "GateContext"]


class ApplyResult(BaseModel):
    """Placeholder for the apply-engine output.

    Template Library epic (2026.06-template-library) will populate this
    model with fields recording the apply operation's outcome. Story 03
    uses it only as a marker for Gate2Validation typing.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


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
