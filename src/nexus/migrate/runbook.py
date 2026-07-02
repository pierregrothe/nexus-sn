# src/nexus/migrate/runbook.py
# Render a MigrationPlan to a lane-shaped, byte-stable runbook (story 05a).
# Author: Pierre Grothe
# Date: 2026-07-02

"""Console + markdown rendering for the migration runbook.

Mirrors ``nexus.replatform.reporter``: a public console summary
(``render_summary``) plus a byte-stable markdown emitter
(``render_runbook`` / ``write_runbook``), split the same way
``render_checklist``/``write_markdown`` are. ``render_runbook`` is pure --
every value in the rendered text derives from the ``MigrationPlan``
argument (and, since story 06, an optional ``DriftReport``), never from
wall-clock time, so two renders of the same plan are byte-identical (AC6).
The runbook's ``generated-at`` header line is not a render timestamp -- it
is the later of the plan's own source/target snapshot timestamps
(ADR-026 Decision 4: freshness is enforced, not assumed), which is why it
stays stable across repeated renders.

Story 06's ``plan --recheck`` reuses this same render path for the STALE
runbook rewrite (AC5) rather than a second, ad hoc output convention: pass
``drift`` and, when it carries drift, a prominent STALE banner renders in
the header, before everything else. ``drift=None`` (the default) renders
byte-identically to story 05's output.
"""

from pathlib import Path

from nexus.migrate.models import (
    Acknowledgment,
    DriftReport,
    IntegrityFinding,
    MigrationPlan,
    PlanItem,
    PlanLane,
    Waiver,
    Wave,
)
from nexus.migrate.planner import validate_approval
from nexus.ui import Notice
from nexus.ui.render_context import RenderContext

__all__ = ["DOCUMENTED_GAPS", "render_runbook", "render_summary", "write_runbook"]

# AC5: fixed documented-gap register -- printed verbatim in every runbook,
# never conditionally omitted. Entries are aligned verbatim to PRD-005's
# "Out of Scope" named-gap sentence (the canonical source; ADR-026's
# Consequences paraphrases it). The v1 closure (Story 04) does not analyze
# any of these; a later story may promote one to an in-tool check.
DOCUMENTED_GAPS: tuple[str, ...] = (
    "script-body scanning (dot-walks, hardcoded sys_ids)",
    "sys_domain separation",
    "legacy Workflow internals closure",
    "notification/email template refs",
    "REST/SOAP message + MID/credential refs",
    "business-rule execution order",
)

_RECHECK_NOTICE = (
    "This runbook reflects a point-in-time snapshot of both instances. Run "
    "`nexus migrate plan --recheck` immediately before executing any wave "
    "by hand to confirm neither instance has drifted since these captures "
    "were taken."
)

_LANE_ADVISORY_NOTICE = (
    "Lane assignment is an advisory routing hint only (ADR-026 Decision 5); "
    "the binding lane/transport architecture is deferred to ADR-027."
)


def render_runbook(plan: MigrationPlan, *, drift: DriftReport | None = None) -> str:
    """Render a MigrationPlan as a lane-shaped, byte-stable markdown runbook.

    Section order: header (AC3) -> approval status (AC7) -> waivers and
    acknowledgments (AC4, before any wave content) -> documented-gap
    register (AC5) -> waves grouped by (wave_index, lane) (AC2).

    Args:
        plan: The assembled MigrationPlan to render.
        drift: A computed DriftReport from a ``plan --recheck`` run (story
            06). When given and ``drift.has_drift``, a STALE banner renders
            in the header before everything else. Default None renders
            byte-identically to story 05's output.

    Returns:
        Markdown text with LF-only line endings (AC6).
    """
    lines: list[str] = []
    lines.extend(_header_lines(plan, drift=drift))
    lines.extend(_approval_lines(plan))
    lines.extend(_waiver_ack_lines(plan))
    lines.extend(_documented_gap_lines())
    lines.extend(_wave_lines(plan))
    lines.append("")
    text = "\n".join(lines)
    # Defensive: free-text fields (Waiver/Acknowledgment reason) are
    # consultant-authored and could carry \r\n; normalize so AC6's "no \r
    # in output" holds regardless of input line endings.
    return text.replace("\r\n", "\n")


def render_summary(plan: MigrationPlan, ctx: RenderContext) -> None:
    """Render a compact console summary of a MigrationPlan (AC1).

    Mirrors ``nexus.replatform.reporter.render_checklist``'s console half;
    ``write_runbook`` is the markdown-file half.

    Args:
        plan: The assembled MigrationPlan to summarize.
        ctx: RenderContext carrying the destination console.
    """
    item_count = sum(len(wave.items) for wave in plan.waves)
    reasons = validate_approval(plan)
    header = (
        f"migration plan {plan.source_profile} -> {plan.target_profile}: "
        f"{len(plan.waves)} wave(s), {item_count} item(s), "
        f"{len(plan.findings)} finding(s), {len(reasons)} blocking reason(s)"
    )
    ctx.console.print(header, highlight=False)
    if reasons:
        ctx.console.print(Notice.warn(f"NOT APPROVED: {len(reasons)} blocking reason(s)"))
    else:
        ctx.console.print(Notice.info("no blocking findings"))


def write_runbook(plan: MigrationPlan, path: Path, *, drift: DriftReport | None = None) -> None:
    """Write the runbook as byte-stable markdown.

    Args:
        plan: The assembled MigrationPlan to render.
        path: Destination file. Always written with LF endings via
            ``write_bytes`` so output is identical across platforms.
        drift: A computed DriftReport from a ``plan --recheck`` run (story
            06); see ``render_runbook``.
    """
    path.write_bytes(render_runbook(plan, drift=drift).encode("utf-8"))


def _stale_banner_lines(drift: DriftReport) -> list[str]:
    """Prominent STALE banner with drift counts per instance/kind (AC5).

    Args:
        drift: The computed DriftReport; only called when ``drift.has_drift``.

    Returns:
        Markdown lines for the STALE banner, one line per non-empty
        instance/kind group.
    """
    lines = ["## STALE -- drift detected since this plan's snapshots", ""]
    groups = (
        ("source", "added", drift.source_added),
        ("source", "removed", drift.source_removed),
        ("source", "changed", drift.source_changed),
        ("target", "added", drift.target_added),
        ("target", "removed", drift.target_removed),
        ("target", "changed", drift.target_changed),
    )
    for instance, kind, keys in groups:
        if keys:
            lines.append(f"- {instance} {kind}: {len(keys)}")
    lines.append("")
    return lines


def _header_lines(plan: MigrationPlan, *, drift: DriftReport | None = None) -> list[str]:
    """Title, optional STALE banner, snapshot identities, and validity window (AC3, AC5).

    ``generated-at`` is deterministic, not wall-clock: the later of the two
    snapshot timestamps the plan was computed from (AC3 + AC6 coexistence).
    """
    generated_at = max(plan.source_captured_at, plan.target_captured_at)
    lines = [f"# Migration Runbook: {plan.source_profile} -> {plan.target_profile}", ""]
    if drift is not None and drift.has_drift:
        lines.extend(_stale_banner_lines(drift))
    lines.extend(
        [
            f"Generated-at (snapshot freshness): {generated_at.isoformat()}",
            "",
            f"Source snapshot: {plan.source_profile} "
            f"captured_at={plan.source_captured_at.isoformat()}",
            f"Target snapshot: {plan.target_profile} "
            f"captured_at={plan.target_captured_at.isoformat()}",
            "",
            f"Validity window: {_RECHECK_NOTICE}",
            "",
        ]
    )
    return lines


def _approval_lines(plan: MigrationPlan) -> list[str]:
    """Front-page approval banner and approval-block state (AC7).

    The banner never claims a tool-side approval state -- it only reports
    whether ``validate_approval`` found blocking reasons; approval itself
    is a human editing the plan YAML (Must Not: the CLI never sets
    ``approved_by``/``approved_at``).
    """
    reasons = validate_approval(plan)
    lines = ["## Approval Status", ""]
    if reasons:
        lines.append(f"NOT APPROVED: {len(reasons)} blocking reason(s):")
        lines.append("")
        lines.extend(f"- {reason}" for reason in reasons)
    else:
        lines.append("No blocking findings.")
    lines.append("")
    if plan.approved_by:
        approved_at = plan.approved_at.isoformat() if plan.approved_at is not None else "(unset)"
        lines.append(f"Approval block: approved_by={plan.approved_by} approved_at={approved_at}")
    else:
        lines.append("Approval block: not yet approved.")
    lines.append("")
    return lines


def _waiver_line(finding: IntegrityFinding, waiver: Waiver) -> str:
    """Render one Waiver verbatim (author, approver, reason, date) (AC4)."""
    return (
        f"- WAIVER on {finding.subject_key!r} ({finding.kind.value}): "
        f"author={waiver.author} approver={waiver.approver} "
        f"reason={waiver.reason!r} date={waiver.date.isoformat()}"
    )


def _acknowledgment_line(finding: IntegrityFinding, ack: Acknowledgment) -> str:
    """Render one Acknowledgment verbatim (author, reason, date) (AC4)."""
    return (
        f"- ACKNOWLEDGMENT on {finding.subject_key!r} ({finding.kind.value}): "
        f"author={ack.author} reason={ack.reason!r} date={ack.date.isoformat()}"
    )


def _waiver_ack_lines(plan: MigrationPlan) -> list[str]:
    """Every Waiver and Acknowledgment, verbatim, before any wave content (AC4)."""
    entries = [_waiver_line(finding, finding.waiver) for finding in plan.findings if finding.waiver]
    entries.extend(
        _acknowledgment_line(finding, finding.acknowledgment)
        for finding in plan.findings
        if finding.acknowledgment
    )
    lines = ["## Waivers and Acknowledgments", ""]
    if entries:
        lines.extend(entries)
    else:
        lines.append("None recorded.")
    lines.append("")
    return lines


def _documented_gap_lines() -> list[str]:
    """Fixed documented-gap register, verbatim, unconditionally rendered (AC5)."""
    lines = ["## Documented gaps (not analyzed by this plan)", ""]
    lines.extend(f"- {gap}" for gap in DOCUMENTED_GAPS)
    lines.append("")
    return lines


def _wave_entry_lines(wave: Wave, lane: PlanLane, items: tuple[PlanItem, ...]) -> list[str]:
    """One lane-shaped runbook entry: a title, item count, and member keys (AC2).

    The unit of work is the (wave, lane) group, not the individual
    artifact -- member keys are listed inside this one entry's body, never
    as top-level runbook lines (Must Not).
    """
    lines = [f"### Wave {wave.index} -- {lane.value} ({len(items)} item(s))", ""]
    for item in items:
        suffix = " (added by closure)" if item.added_by_closure else ""
        lines.append(f"- {item.key}{suffix}")
    lines.append("")
    return lines


def _wave_lines(plan: MigrationPlan) -> list[str]:
    """Lane-shaped wave entries: one entry per (wave_index, lane) group (AC2)."""
    lines = ["## Waves", "", _LANE_ADVISORY_NOTICE, ""]
    for wave in plan.waves:
        for lane in PlanLane:
            group = tuple(item for item in wave.items if item.lane is lane)
            if not group:
                continue
            lines.extend(_wave_entry_lines(wave, lane, group))
    return lines
