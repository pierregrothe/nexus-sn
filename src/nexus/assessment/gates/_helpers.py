# src/nexus/assessment/gates/_helpers.py
# Shared helpers across gate implementations.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Internal helpers reused by readiness/validation/health gates."""

from __future__ import annotations

from nexus.assessment.findings import Finding
from nexus.assessment.report import GateReport
from nexus.assessment.schemas.enums import Phase, Severity

__all__ = ["phase_mismatch_report"]


def phase_mismatch_report(
    *, ruleset_id: str, template_id: str | None, expected: Phase, got: Phase
) -> GateReport:
    """Build an ERROR GateReport when a gate is invoked with the wrong phase."""
    finding = Finding(
        rule_id="_gate_phase_mismatch",
        severity=Severity.ERROR,
        message=f"gate requires ctx.phase={expected.value}, got {got.value}",
        affected_sys_ids=(),
        phase=got,
    )
    return GateReport.from_findings(
        (finding,),
        rules_evaluated=0,
        ruleset_id=ruleset_id,
        template_id=template_id,
        phase=got,
    )
