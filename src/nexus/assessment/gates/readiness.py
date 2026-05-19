# src/nexus/assessment/gates/readiness.py
# Gate1Readiness -- pre-apply readiness check.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Gate 1: evaluate PRE_APPLY rules against a pre-apply capture."""

from __future__ import annotations

from dataclasses import dataclass

from nexus.assessment.context import GateContext
from nexus.assessment.engine import evaluate
from nexus.assessment.gates._helpers import phase_mismatch_report
from nexus.assessment.report import GateReport
from nexus.assessment.schemas.enums import Phase
from nexus.assessment.schemas.ruleset import Ruleset

__all__ = ["Gate1Readiness"]


@dataclass(slots=True, frozen=True)
class Gate1Readiness:
    """Pre-apply readiness gate.

    Attributes:
        ruleset: Ruleset whose PRE_APPLY rules will run.
        template_id: Template id the gate is acting for.
    """

    ruleset: Ruleset
    template_id: str

    def evaluate(self, ctx: GateContext) -> GateReport:
        """Evaluate PRE_APPLY rules from `self.ruleset` against ctx."""
        if ctx.phase is not Phase.PRE_APPLY:
            return phase_mismatch_report(
                ruleset_id=self.ruleset.id,
                template_id=self.template_id,
                expected=Phase.PRE_APPLY,
                got=ctx.phase,
            )
        relevant = tuple(rule for rule in self.ruleset.rules if rule.phase is Phase.PRE_APPLY)
        findings = evaluate(relevant, ctx)
        return GateReport.from_findings(
            findings,
            rules_evaluated=len(relevant),
            ruleset_id=self.ruleset.id,
            template_id=self.template_id,
            phase=Phase.PRE_APPLY,
        )
