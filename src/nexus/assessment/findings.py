# src/nexus/assessment/findings.py
# Finding model emitted by RuleEngine.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Frozen Pydantic Finding model carried in GateReport."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from nexus.assessment.schemas.enums import Phase, Severity

__all__ = ["Finding"]


class Finding(BaseModel):
    """One observable failure or error produced by RuleEngine.evaluate.

    Attributes:
        rule_id: Identifier of the AssessmentRule that produced the Finding.
        severity: Per-rule severity from AssessmentRule.severity, or ERROR
            for engine-emitted findings (capture-completeness, rule-load).
        message: Human-readable summary used by the reporter.
        affected_sys_ids: Tuple of ConfigRecord sys_ids the Finding refers to.
        phase: Phase from the GateContext when the rule was evaluated.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    rule_id: str = Field(..., min_length=1)
    severity: Severity
    message: str = Field(..., min_length=1)
    affected_sys_ids: tuple[str, ...] = ()
    phase: Phase
