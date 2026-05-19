# tests/assessment/test_reporter.py
# Tests for AssessmentReporter.render_report.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 05 AC1-AC10: reporter layout, severity order, PLAIN profile."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from nexus.assessment.findings import Finding
from nexus.assessment.report import GateReport
from nexus.assessment.reporter import render_report
from nexus.assessment.schemas.enums import Phase, Severity
from nexus.assessment.verdict import GateVerdict
from nexus.ui.capabilities import (
    ColorDepth,
    RenderProfile,
    TerminalCapabilities,
)
from nexus.ui.render_context import RenderContext
from nexus.ui.theme import NEXUS_THEME


def _render_context(profile: RenderProfile) -> RenderContext:
    console = Console(
        file=StringIO(),
        width=120,
        force_terminal=profile is not RenderProfile.PLAIN,
        record=True,
        theme=NEXUS_THEME,
        color_system="truecolor" if profile is RenderProfile.RICH else None,
    )
    caps = TerminalCapabilities(
        is_tty=profile is not RenderProfile.PLAIN,
        is_ci=False,
        color_depth=ColorDepth.TRUECOLOR if profile is RenderProfile.RICH else ColorDepth.NONE,
        cols=120,
        rows=40,
        legacy_windows=False,
        term_program="",
        is_dumb_terminal=False,
        is_multiplexer=False,
        no_color_env=False,
        forced_plain=profile is RenderProfile.PLAIN,
        supports_hyperlinks=profile is RenderProfile.RICH,
    )
    return RenderContext(console=console, caps=caps, profile=profile)


def _report(
    verdict: GateVerdict,
    *,
    findings: tuple[Finding, ...] = (),
    template_id: str | None = "acme",
) -> GateReport:
    return GateReport.from_findings(
        findings,
        rules_evaluated=max(1, len(findings)),
        ruleset_id="rs",
        template_id=template_id,
        phase=Phase.PRE_APPLY,
    )


def test_render_report_pass_on_rich_profile_prints_notice_and_badge() -> None:
    ctx = _render_context(RenderProfile.RICH)
    report = _report(GateVerdict.PASS)
    render_report(report, ctx)
    output = ctx.console.export_text()
    assert "Info:" in output
    assert "PASS" in output


def test_render_report_block_on_rich_profile_prints_error_notice_and_hint() -> None:
    ctx = _render_context(RenderProfile.RICH)
    finding = Finding(
        rule_id="r1",
        severity=Severity.WARNING,
        message="scope not active",
        affected_sys_ids=("s1",),
        phase=Phase.PRE_APPLY,
    )
    report = _report(GateVerdict.BLOCK, findings=(finding,))
    render_report(report, ctx)
    output = ctx.console.export_text()
    assert "Error:" in output
    assert "BLOCK" in output
    assert "Bypass" in output
    assert "--force" in output


def test_render_report_error_on_rich_profile_prints_warn_badge_and_retry_hint() -> None:
    ctx = _render_context(RenderProfile.RICH)
    finding = Finding(
        rule_id="r1",
        severity=Severity.ERROR,
        message="required table missing",
        affected_sys_ids=(),
        phase=Phase.PRE_APPLY,
    )
    report = _report(GateVerdict.ERROR, findings=(finding,))
    render_report(report, ctx)
    output = ctx.console.export_text()
    assert "ERROR" in output
    assert "Retry" in output
    assert "--live" in output


def test_render_report_plain_profile_uses_ascii_lines_no_table() -> None:
    ctx = _render_context(RenderProfile.PLAIN)
    finding = Finding(
        rule_id="r1",
        severity=Severity.ERROR,
        message="boom",
        affected_sys_ids=("a", "b"),
        phase=Phase.PRE_APPLY,
    )
    report = _report(GateVerdict.ERROR, findings=(finding,))
    render_report(report, ctx)
    output = ctx.console.export_text()
    assert "[ERROR]" in output
    assert "r1" in output
    assert "affected: 2" in output


def test_render_report_findings_sorted_by_severity_error_first() -> None:
    ctx = _render_context(RenderProfile.RICH)
    info_finding = Finding(
        rule_id="info-1",
        severity=Severity.INFO,
        message="ok",
        affected_sys_ids=(),
        phase=Phase.PRE_APPLY,
    )
    error_finding = Finding(
        rule_id="err-1",
        severity=Severity.ERROR,
        message="bad",
        affected_sys_ids=(),
        phase=Phase.PRE_APPLY,
    )
    report = _report(GateVerdict.ERROR, findings=(info_finding, error_finding))
    render_report(report, ctx)
    output = ctx.console.export_text()
    assert output.index("err-1") < output.index("info-1")


def test_render_report_long_message_truncates_with_ellipsis() -> None:
    ctx = _render_context(RenderProfile.RICH)
    long_message = "x" * 200
    finding = Finding(
        rule_id="r",
        severity=Severity.ERROR,
        message=long_message,
        affected_sys_ids=(),
        phase=Phase.PRE_APPLY,
    )
    report = _report(GateVerdict.ERROR, findings=(finding,))
    render_report(report, ctx)
    output = ctx.console.export_text()
    assert "..." in output


def test_render_report_omits_template_row_when_template_id_none() -> None:
    ctx = _render_context(RenderProfile.RICH)
    report = _report(GateVerdict.PASS, template_id=None)
    render_report(report, ctx)
    output = ctx.console.export_text()
    assert "template:" not in output


def test_render_report_includes_template_row_when_set() -> None:
    ctx = _render_context(RenderProfile.RICH)
    report = _report(GateVerdict.PASS, template_id="acme")
    render_report(report, ctx)
    output = ctx.console.export_text()
    assert "template" in output
    assert "acme" in output


def test_render_report_pass_omits_findings_table() -> None:
    ctx = _render_context(RenderProfile.RICH)
    report = _report(GateVerdict.PASS)
    render_report(report, ctx)
    output = ctx.console.export_text()
    assert "Findings" not in output
