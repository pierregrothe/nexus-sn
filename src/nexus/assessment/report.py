# src/nexus/assessment/report.py
# GateReport + GateSummary.
# Author: Pierre Grothe
# Date: 2026-05-19

"""GateReport: uniform output shape returned by every GateProtocol impl."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from nexus.assessment.findings import Finding
from nexus.assessment.schemas.enums import Phase, Severity
from nexus.assessment.verdict import GateVerdict

__all__ = ["GateReport", "GateSummary"]


class GateSummary(BaseModel):
    """Aggregated counts used by the reporter for the summary panel."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    rules_evaluated: int = Field(..., ge=0)
    rules_passed: int = Field(..., ge=0)
    rules_failed: int = Field(..., ge=0)
    rules_errored: int = Field(..., ge=0)
    affected_records: int = Field(..., ge=0)


class GateReport(BaseModel):
    """Outcome of one gate.evaluate call.

    Attributes:
        verdict: PASS / BLOCK / ERROR derived from findings + phase.
        findings: All findings emitted by the engine.
        summary: GateSummary aggregate counts.
        ruleset_id: Identifier of the ruleset evaluated (None when none ran).
        template_id: Template the gate ran for (None for HealthScan).
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    verdict: GateVerdict
    findings: tuple[Finding, ...] = ()
    summary: GateSummary
    ruleset_id: str | None = None
    template_id: str | None = None

    @classmethod
    def from_findings(
        cls,
        findings: tuple[Finding, ...],
        *,
        rules_evaluated: int,
        ruleset_id: str | None,
        template_id: str | None,
        phase: Phase,
    ) -> Self:
        """Build a GateReport with verdict derived from findings + phase.

        Verdict rules:
            - any Finding(severity=ERROR) -> verdict=ERROR
            - any Finding(severity=WARNING) and phase=PRE_APPLY -> BLOCK
            - any Finding(severity=WARNING) elsewhere -> PASS (advisory)
            - only INFO findings (or none) -> PASS

        Args:
            findings: Tuple of Findings produced by RuleEngine.evaluate.
            rules_evaluated: Count of rules the engine actually ran
                (post phase-filter, including those that produced
                completeness ERRORs).
            ruleset_id: Ruleset identifier for reporter display.
            template_id: Template the gate ran for, or None.
            phase: Phase of the gate (used by verdict derivation).

        Returns:
            A GateReport with verdict and summary computed from findings.
        """
        has_error = any(f.severity is Severity.ERROR for f in findings)
        has_warning = any(f.severity is Severity.WARNING for f in findings)
        verdict = _derive_verdict(has_error=has_error, has_warning=has_warning, phase=phase)
        errored = sum(1 for f in findings if f.severity is Severity.ERROR)
        failed_or_warn = sum(1 for f in findings if f.severity is not Severity.ERROR)
        passed = max(0, rules_evaluated - len(findings))
        affected = len({sys_id for f in findings for sys_id in f.affected_sys_ids})
        summary = GateSummary(
            rules_evaluated=rules_evaluated,
            rules_passed=passed,
            rules_failed=failed_or_warn,
            rules_errored=errored,
            affected_records=affected,
        )
        return cls(
            verdict=verdict,
            findings=findings,
            summary=summary,
            ruleset_id=ruleset_id,
            template_id=template_id,
        )


def _derive_verdict(*, has_error: bool, has_warning: bool, phase: Phase) -> GateVerdict:
    """Map (has_error, has_warning, phase) to a GateVerdict."""
    if has_error:
        return GateVerdict.ERROR
    if has_warning and phase is Phase.PRE_APPLY:
        return GateVerdict.BLOCK
    return GateVerdict.PASS
