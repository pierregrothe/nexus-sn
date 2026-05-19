# tests/assessment/test_gate_report.py
# Tests for GateReport + GateSummary + verdict derivation.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 04 AC3, AC4: GateReport.from_findings verdict logic."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexus.assessment.findings import Finding
from nexus.assessment.report import GateReport, GateSummary
from nexus.assessment.schemas.enums import Phase, Severity
from nexus.assessment.verdict import GateVerdict


def _finding(severity: Severity, *, phase: Phase = Phase.PRE_APPLY) -> Finding:
    return Finding(
        rule_id="r",
        severity=severity,
        message="m",
        affected_sys_ids=("sid",),
        phase=phase,
    )


def test_from_findings_with_empty_returns_pass() -> None:
    report = GateReport.from_findings(
        (),
        rules_evaluated=2,
        ruleset_id="rs",
        template_id="t",
        phase=Phase.PRE_APPLY,
    )
    assert report.verdict is GateVerdict.PASS
    assert report.summary.rules_passed == 2
    assert report.summary.rules_failed == 0


def test_from_findings_with_any_error_returns_error_verdict() -> None:
    findings = (
        _finding(Severity.WARNING),
        _finding(Severity.ERROR),
    )
    report = GateReport.from_findings(
        findings,
        rules_evaluated=3,
        ruleset_id="rs",
        template_id="t",
        phase=Phase.PRE_APPLY,
    )
    assert report.verdict is GateVerdict.ERROR
    assert report.summary.rules_errored == 1
    assert report.summary.rules_failed == 1


def test_from_findings_with_warning_in_pre_apply_blocks() -> None:
    findings = (_finding(Severity.WARNING),)
    report = GateReport.from_findings(
        findings,
        rules_evaluated=1,
        ruleset_id="rs",
        template_id="t",
        phase=Phase.PRE_APPLY,
    )
    assert report.verdict is GateVerdict.BLOCK


def test_from_findings_with_warning_in_post_apply_passes() -> None:
    findings = (_finding(Severity.WARNING, phase=Phase.POST_APPLY),)
    report = GateReport.from_findings(
        findings,
        rules_evaluated=1,
        ruleset_id="rs",
        template_id="t",
        phase=Phase.POST_APPLY,
    )
    assert report.verdict is GateVerdict.PASS


def test_from_findings_with_warning_in_standalone_passes() -> None:
    findings = (_finding(Severity.WARNING, phase=Phase.STANDALONE),)
    report = GateReport.from_findings(
        findings,
        rules_evaluated=1,
        ruleset_id="rs",
        template_id=None,
        phase=Phase.STANDALONE,
    )
    assert report.verdict is GateVerdict.PASS


def test_from_findings_with_only_info_passes_in_all_phases() -> None:
    findings = (_finding(Severity.INFO),)
    for phase in (Phase.PRE_APPLY, Phase.POST_APPLY, Phase.STANDALONE):
        report = GateReport.from_findings(
            findings,
            rules_evaluated=1,
            ruleset_id="rs",
            template_id="t",
            phase=phase,
        )
        assert report.verdict is GateVerdict.PASS


def test_from_findings_summary_counts_affected_records() -> None:
    findings = (
        Finding(
            rule_id="r",
            severity=Severity.ERROR,
            message="m",
            affected_sys_ids=("a", "b", "a"),
            phase=Phase.PRE_APPLY,
        ),
        Finding(
            rule_id="r2",
            severity=Severity.ERROR,
            message="m",
            affected_sys_ids=("c",),
            phase=Phase.PRE_APPLY,
        ),
    )
    report = GateReport.from_findings(
        findings,
        rules_evaluated=2,
        ruleset_id="rs",
        template_id="t",
        phase=Phase.PRE_APPLY,
    )
    assert report.summary.affected_records == 3


def test_gate_summary_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        GateSummary(
            rules_evaluated=-1,
            rules_passed=0,
            rules_failed=0,
            rules_errored=0,
            affected_records=0,
        )


def test_gate_report_is_frozen() -> None:
    report = GateReport.from_findings(
        (),
        rules_evaluated=0,
        ruleset_id="rs",
        template_id="t",
        phase=Phase.PRE_APPLY,
    )
    with pytest.raises(ValidationError):
        report.verdict = GateVerdict.BLOCK
