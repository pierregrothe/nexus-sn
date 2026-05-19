# src/nexus/assessment/gates/health.py
# HealthScan -- standalone instance health check.
# Author: Pierre Grothe
# Date: 2026-05-19

"""HealthScan: evaluate STANDALONE rules for `nexus assess` (no flags)."""

from __future__ import annotations

from dataclasses import dataclass

from nexus.assessment.context import GateContext
from nexus.assessment.engine import evaluate
from nexus.assessment.gates._helpers import phase_mismatch_report
from nexus.assessment.report import GateReport
from nexus.assessment.schemas.enums import Phase
from nexus.assessment.schemas.ruleset import Ruleset

__all__ = ["HealthScan"]


@dataclass(slots=True, frozen=True)
class HealthScan:
    """Standalone health-scan gate.

    Attributes:
        ruleset: Ruleset whose STANDALONE rules will run.
    """

    ruleset: Ruleset

    def evaluate(self, ctx: GateContext) -> GateReport:
        """Evaluate STANDALONE rules from `self.ruleset` against ctx."""
        if ctx.phase is not Phase.STANDALONE:
            return phase_mismatch_report(
                ruleset_id=self.ruleset.id,
                template_id=None,
                expected=Phase.STANDALONE,
                got=ctx.phase,
            )
        relevant = tuple(rule for rule in self.ruleset.rules if rule.phase is Phase.STANDALONE)
        findings = evaluate(relevant, ctx)
        return GateReport.from_findings(
            findings,
            rules_evaluated=len(relevant),
            ruleset_id=self.ruleset.id,
            template_id=None,
            phase=Phase.STANDALONE,
        )
