# src/nexus/assessment/reporter.py
# AssessmentReporter: render a GateReport to the console.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Render a GateReport via the existing ui/components/ primitives.

Layout per verdict:
    PASS  -> Notice.info(...) + StatusBadge(PASS, ok) + KeyValuePanel summary
    BLOCK -> Notice.error(...) + StatusBadge(BLOCK, error) + summary + table
             + Hint("--force")
    ERROR -> Notice.error(...) + StatusBadge(ERROR, warn) + summary + table
             + Hint("re-run with --live")

PLAIN profile bypasses Rich primitives and prints one ASCII line per event.
"""

from __future__ import annotations

from rich.console import RenderableType

from nexus.assessment.findings import Finding
from nexus.assessment.report import GateReport
from nexus.assessment.schemas.enums import Severity
from nexus.assessment.verdict import GateVerdict
from nexus.ui.capabilities import RenderProfile
from nexus.ui.components import (
    DataColumn,
    DataTable,
    Hint,
    KeyValuePanel,
    KvRow,
    Notice,
    StatusBadge,
)
from nexus.ui.render_context import RenderContext

__all__ = ["render_report"]


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.ERROR: 0,
    Severity.WARNING: 1,
    Severity.INFO: 2,
}

_MESSAGE_LIMIT: int = 80


def render_report(report: GateReport, ctx: RenderContext) -> None:
    """Render a GateReport to `ctx.console`.

    Args:
        report: GateReport to display.
        ctx: RenderContext carrying the destination console + profile.
    """
    if ctx.profile is RenderProfile.PLAIN:
        _render_plain(report, ctx)
        return
    _render_rich(report, ctx)


def _render_plain(report: GateReport, ctx: RenderContext) -> None:
    """One ASCII line per event for PLAIN profile."""
    header = (
        f"[{report.verdict.value}] gate ruleset={report.ruleset_id or '-'}"
        f" template={report.template_id or '-'} findings={len(report.findings)}"
    )
    ctx.console.print(header, highlight=False)
    for finding in _sort_findings(report.findings):
        affected = len(finding.affected_sys_ids)
        ctx.console.print(
            f"[{finding.severity.value}] {finding.rule_id}: "
            f"{finding.message} (affected: {affected})",
            highlight=False,
        )


def _render_rich(report: GateReport, ctx: RenderContext) -> None:
    """RICH / BASIC / LEGACY rendering using ui/components/."""
    ctx.console.print(_notice_for(report))
    ctx.console.print(_badge_for(report))
    ctx.console.print(_summary_panel(report))
    if report.findings:
        ctx.console.print(_findings_table(report))
    hint = _hint_for(report)
    if hint is not None:
        ctx.console.print(hint)


def _notice_for(report: GateReport) -> Notice:
    """Notice line at the top of the rich layout."""
    findings_count = len(report.findings)
    match report.verdict:
        case GateVerdict.PASS:
            return Notice.info(f"gate PASS: {report.summary.rules_evaluated} rules evaluated")
        case GateVerdict.BLOCK:
            return Notice.error(f"gate BLOCK: {findings_count} finding(s)")
        case GateVerdict.ERROR:
            return Notice.error(f"gate ERROR: evaluation incomplete ({findings_count} issue(s))")
        case _:  # pragma: no cover -- exhaustive over GateVerdict
            raise AssertionError(f"unreachable verdict: {report.verdict!r}")


def _badge_for(report: GateReport) -> StatusBadge:
    """Verdict badge rendered after the Notice line."""
    match report.verdict:
        case GateVerdict.PASS:
            return StatusBadge.ok("PASS")
        case GateVerdict.BLOCK:
            return StatusBadge.error("BLOCK")
        case GateVerdict.ERROR:
            return StatusBadge.warn("ERROR")
        case _:  # pragma: no cover -- exhaustive over GateVerdict
            raise AssertionError(f"unreachable verdict: {report.verdict!r}")


def _summary_panel(report: GateReport) -> KeyValuePanel:
    """Build the KeyValuePanel showing GateSummary counts + ruleset metadata."""
    rows: list[KvRow] = []
    if report.template_id is not None:
        rows.append(KvRow(label="template", value=report.template_id))
    rows.append(KvRow(label="ruleset", value=report.ruleset_id or "-"))
    rows.append(KvRow(label="rules evaluated", value=str(report.summary.rules_evaluated)))
    rows.append(KvRow(label="passed", value=str(report.summary.rules_passed)))
    rows.append(KvRow(label="failed", value=str(report.summary.rules_failed)))
    rows.append(KvRow(label="errored", value=str(report.summary.rules_errored)))
    rows.append(KvRow(label="affected records", value=str(report.summary.affected_records)))
    return KeyValuePanel(title="Gate Summary", rows=rows)


def _findings_table(report: GateReport) -> DataTable:
    """Build a DataTable of findings sorted by severity."""
    rows: list[list[RenderableType]] = []
    for finding in _sort_findings(report.findings):
        message = _truncate(finding.message, _MESSAGE_LIMIT)
        rows.append(
            [
                finding.rule_id,
                finding.severity.value,
                str(len(finding.affected_sys_ids)),
                message,
            ]
        )
    columns = [
        DataColumn(header="rule_id", min_width=12, no_wrap=True),
        DataColumn(header="severity", min_width=8, no_wrap=True),
        DataColumn(header="affected", min_width=8, justify="right", no_wrap=True),
        DataColumn(header="message", min_width=20, no_wrap=False),
    ]
    return DataTable(title="Findings", columns=columns, rows=rows)


def _hint_for(report: GateReport) -> Hint | None:
    """Build a Hint pointing at remediation when verdict isn't PASS."""
    match report.verdict:
        case GateVerdict.PASS:
            return None
        case GateVerdict.BLOCK:
            return Hint(
                label="Bypass",
                command="nexus apply --force",
                suffix="(skips Gate 1 verdict only)",
            )
        case GateVerdict.ERROR:
            return Hint(
                label="Retry",
                command="nexus assess --live",
                suffix="(re-capture from the live instance)",
            )
        case _:  # pragma: no cover -- exhaustive over GateVerdict
            raise AssertionError(f"unreachable verdict: {report.verdict!r}")


def _sort_findings(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """Sort by severity (ERROR -> WARNING -> INFO) preserving input order within tier."""
    return tuple(sorted(findings, key=lambda f: _SEVERITY_ORDER[f.severity]))


def _truncate(text: str, limit: int) -> str:
    """Truncate `text` to `limit` chars with ellipsis if longer."""
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."
