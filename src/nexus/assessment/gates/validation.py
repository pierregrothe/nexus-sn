# src/nexus/assessment/gates/validation.py
# Gate2Validation -- post-apply validation check.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Gate 2: evaluate POST_APPLY rules against a post-apply capture."""

from __future__ import annotations

from dataclasses import dataclass

from nexus.assessment.context import GateContext
from nexus.assessment.engine import evaluate
from nexus.assessment.findings import Finding
from nexus.assessment.gates._helpers import phase_mismatch_report
from nexus.assessment.report import GateReport
from nexus.assessment.schemas.enums import Phase, Severity
from nexus.assessment.schemas.ruleset import Ruleset

__all__ = ["Gate2Validation"]


@dataclass(slots=True, frozen=True)
class Gate2Validation:
    """Post-apply validation gate.

    Attributes:
        ruleset: Ruleset whose POST_APPLY rules will run.
        template_id: Template id the gate is acting for.
    """

    ruleset: Ruleset
    template_id: str

    def evaluate(self, ctx: GateContext) -> GateReport:
        """Evaluate POST_APPLY rules from `self.ruleset` against ctx."""
        if ctx.phase is not Phase.POST_APPLY:
            return phase_mismatch_report(
                ruleset_id=self.ruleset.id,
                template_id=self.template_id,
                expected=Phase.POST_APPLY,
                got=ctx.phase,
            )
        if ctx.apply_result is None:
            return _missing_apply_result_report(self.ruleset.id, self.template_id)
        relevant = tuple(rule for rule in self.ruleset.rules if rule.phase is Phase.POST_APPLY)
        findings = evaluate(relevant, ctx)
        return GateReport.from_findings(
            findings,
            rules_evaluated=len(relevant),
            ruleset_id=self.ruleset.id,
            template_id=self.template_id,
            phase=Phase.POST_APPLY,
        )


def _missing_apply_result_report(ruleset_id: str, template_id: str) -> GateReport:
    """Build an ERROR report when Gate 2 has no apply_result to consult."""
    finding = Finding(
        rule_id="_gate2_missing_apply_result",
        severity=Severity.ERROR,
        message="Gate2 requires apply_result; got None",
        affected_sys_ids=(),
        phase=Phase.POST_APPLY,
    )
    return GateReport.from_findings(
        (finding,),
        rules_evaluated=0,
        ruleset_id=ruleset_id,
        template_id=template_id,
        phase=Phase.POST_APPLY,
    )
