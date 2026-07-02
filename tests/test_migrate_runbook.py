# tests/test_migrate_runbook.py
# Tests for nexus.migrate.runbook (story 05a): AC2-AC6.
# Author: Pierre Grothe
# Date: 2026-07-02

"""AC2-AC6: lane-shaped grouping, header, waiver/ack front page, gap register,
byte-stability, and the AC7 approval banner.

No mocks; every MigrationPlan/Wave/PlanItem/IntegrityFinding fixture comes
from tests/fakes/migrate.py or is built directly (frozen Pydantic models).
"""

from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from rich.console import Console

from nexus.migrate.models import DriftReport, FindingKind, MigrationPlan, PlanLane
from nexus.migrate.planner import validate_approval
from nexus.migrate.runbook import DOCUMENTED_GAPS, render_runbook, render_summary, write_runbook
from nexus.ui.capabilities import ColorDepth, RenderProfile, TerminalCapabilities
from nexus.ui.render_context import RenderContext
from nexus.ui.theme import NEXUS_THEME
from tests.fakes.migrate import (
    make_acknowledgment,
    make_integrity_finding,
    make_migration_plan,
    make_plan_item,
    make_waiver,
    make_wave,
)

_TS = datetime(2026, 7, 2, 12, 0, 0, tzinfo=UTC)


def _ctx(buf: StringIO) -> RenderContext:
    console = Console(file=buf, width=120, record=True, theme=NEXUS_THEME, force_terminal=False)
    caps = TerminalCapabilities(
        is_tty=False,
        is_ci=False,
        color_depth=ColorDepth.NONE,
        cols=120,
        rows=40,
        legacy_windows=False,
        term_program="",
        is_dumb_terminal=False,
        is_multiplexer=False,
        no_color_env=False,
        forced_plain=True,
        supports_hyperlinks=False,
    )
    return RenderContext(console=console, caps=caps, profile=RenderProfile.PLAIN)


def _multi_lane_plan() -> MigrationPlan:
    """A two-wave plan whose first wave spans two lanes (AC2 grouping fixture)."""
    wave0_items = (
        make_plan_item(key="x_app|sys_hub_flow|approve po", lane=PlanLane.UPDATE_SET, wave_index=0),
        make_plan_item(
            key="x_app|sys_hub_flow|reject po",
            lane=PlanLane.UPDATE_SET,
            wave_index=0,
            added_by_closure=True,
        ),
        make_plan_item(
            key="x_app|sys_app_application|acme app", lane=PlanLane.APP_REPO, wave_index=0
        ),
    )
    wave1_items = (
        make_plan_item(key="x_app|sys_db_object|po_request", lane=PlanLane.DATA, wave_index=1),
    )
    return make_migration_plan(
        waves=(make_wave(index=0, items=wave0_items), make_wave(index=1, items=wave1_items)),
        findings=(),
    )


# -- AC2: lane-shaped grouping -------------------------------------------------


def test_render_runbook_groups_items_by_wave_and_lane_into_one_entry_each() -> None:
    text = render_runbook(_multi_lane_plan())

    assert text.count("### Wave") == 3
    assert "### Wave 0 -- UPDATE_SET (2 item(s))" in text
    assert "### Wave 0 -- APP_REPO (1 item(s))" in text
    assert "### Wave 1 -- DATA (1 item(s))" in text


def test_render_runbook_lists_member_keys_inside_the_lane_entry() -> None:
    text = render_runbook(_multi_lane_plan())

    entry_start = text.index("### Wave 0 -- UPDATE_SET")
    entry_end = text.index("### Wave 1 -- DATA")
    entry_body = text[entry_start:entry_end]
    assert "x_app|sys_hub_flow|approve po" in entry_body
    assert "x_app|sys_hub_flow|reject po (added by closure)" in entry_body


# -- AC3: runbook header -------------------------------------------------------


def test_render_runbook_header_carries_generated_at_and_snapshot_identities() -> None:
    plan = make_migration_plan(
        source_profile="alectri",
        target_profile="retail",
        source_captured_at=datetime(2026, 7, 1, 10, 0, 0, tzinfo=UTC),
        target_captured_at=datetime(2026, 7, 2, 15, 30, 0, tzinfo=UTC),
    )

    text = render_runbook(plan)

    assert "Generated-at (snapshot freshness): 2026-07-02T15:30:00+00:00" in text
    assert "Source snapshot: alectri captured_at=2026-07-01T10:00:00+00:00" in text
    assert "Target snapshot: retail captured_at=2026-07-02T15:30:00+00:00" in text
    assert "plan --recheck" in text


def test_render_runbook_generated_at_is_the_later_of_the_two_snapshots() -> None:
    plan = make_migration_plan(
        source_captured_at=datetime(2026, 7, 5, 0, 0, 0, tzinfo=UTC),
        target_captured_at=datetime(2026, 7, 1, 0, 0, 0, tzinfo=UTC),
    )

    text = render_runbook(plan)

    assert "Generated-at (snapshot freshness): 2026-07-05T00:00:00+00:00" in text


# -- AC4: waiver/acknowledgment front page -------------------------------------


def test_render_runbook_places_waivers_and_acks_before_any_wave_content() -> None:
    waiver = make_waiver(
        author="alice", approver="bob", reason="manual post-migration step", date=_TS
    )
    ack = make_acknowledgment(author="carol", reason="data seeded out of band", date=_TS)
    findings = (
        make_integrity_finding(
            kind=FindingKind.STRANDED_DEPENDENCY, subject_key="k1", detail="d1", waiver=waiver
        ),
        make_integrity_finding(
            kind=FindingKind.DATA_PREREQUISITE, subject_key="k2", detail="d2", acknowledgment=ack
        ),
    )
    plan = make_migration_plan(findings=findings)

    text = render_runbook(plan)

    assert "alice" in text
    assert "bob" in text
    assert "manual post-migration step" in text
    assert "carol" in text
    assert "data seeded out of band" in text
    wave_idx = text.index("### Wave")
    assert text.index("WAIVER") < wave_idx
    assert text.index("ACKNOWLEDGMENT") < wave_idx


def test_render_runbook_reports_none_recorded_when_no_waivers_or_acks() -> None:
    plan = make_migration_plan(findings=())

    text = render_runbook(plan)

    assert "## Waivers and Acknowledgments" in text
    assert "None recorded." in text


# -- AC5: documented-gap register ----------------------------------------------


def test_documented_gaps_match_prd_005_out_of_scope_verbatim() -> None:
    # Canonical source: .primer/prd/PRD-005-nexus-migration-planner.md#Out of
    # Scope, the named-gap sentence -- ADR-026's Consequences paraphrases it.
    assert DOCUMENTED_GAPS == (
        "script-body scanning (dot-walks, hardcoded sys_ids)",
        "sys_domain separation",
        "legacy Workflow internals closure",
        "notification/email template refs",
        "REST/SOAP message + MID/credential refs",
        "business-rule execution order",
    )


def test_render_runbook_includes_documented_gap_register_verbatim_for_minimal_plan() -> None:
    plan = make_migration_plan(waves=(), findings=())

    text = render_runbook(plan)

    for gap in DOCUMENTED_GAPS:
        assert gap in text


def test_render_runbook_includes_documented_gap_register_when_plan_has_content() -> None:
    text = render_runbook(_multi_lane_plan())

    for gap in DOCUMENTED_GAPS:
        assert gap in text


# -- AC6: byte-stable LF output -------------------------------------------------


def test_render_runbook_is_byte_stable_across_renders() -> None:
    plan = make_migration_plan()

    first = render_runbook(plan)
    second = render_runbook(plan)

    assert first == second
    assert "\r" not in first


def test_render_runbook_normalizes_crlf_in_free_text_fields() -> None:
    waiver = make_waiver(reason="line one\r\nline two", date=_TS)
    finding = make_integrity_finding(waiver=waiver)
    plan = make_migration_plan(findings=(finding,))

    text = render_runbook(plan)

    assert "\r" not in text


# -- AC7: unapproved plan front-page banner ------------------------------------


def test_render_runbook_flags_not_approved_with_blocking_reasons_verbatim() -> None:
    finding = make_integrity_finding(
        kind=FindingKind.STRANDED_DEPENDENCY, subject_key="k1", waiver=None
    )
    plan = make_migration_plan(findings=(finding,))
    reasons = validate_approval(plan)

    text = render_runbook(plan)

    assert f"NOT APPROVED: {len(reasons)} blocking reason(s):" in text
    for reason in reasons:
        assert reason in text


def test_render_runbook_omits_not_approved_banner_when_no_blocking_findings() -> None:
    plan = make_migration_plan(findings=())

    text = render_runbook(plan)

    assert "NOT APPROVED" not in text
    assert "No blocking findings." in text


def test_render_runbook_renders_approval_block_when_approved() -> None:
    plan = make_migration_plan(approved_by="alice", approved_at=_TS, findings=())

    text = render_runbook(plan)

    assert f"Approval block: approved_by=alice approved_at={_TS.isoformat()}" in text
    assert "not yet approved" not in text


def test_render_runbook_renders_not_yet_approved_when_unset() -> None:
    plan = make_migration_plan(findings=())

    text = render_runbook(plan)

    assert "Approval block: not yet approved." in text


# -- render_summary / write_runbook (console + file split) --------------------


def test_render_summary_prints_counts_and_no_blocking_notice() -> None:
    plan = make_migration_plan(findings=())
    buf = StringIO()

    render_summary(plan, _ctx(buf))

    output = buf.getvalue()
    assert "migration plan alectri -> retail" in output
    assert "0 blocking reason(s)" in output
    assert "no blocking findings" in output


def test_render_summary_prints_not_approved_notice_when_blocking() -> None:
    finding = make_integrity_finding(kind=FindingKind.STRANDED_DEPENDENCY, waiver=None)
    plan = make_migration_plan(findings=(finding,))
    buf = StringIO()

    render_summary(plan, _ctx(buf))

    assert "NOT APPROVED: 1 blocking reason(s)" in buf.getvalue()


def test_write_runbook_writes_byte_stable_markdown_matching_render_runbook(tmp_path: Path) -> None:
    plan = make_migration_plan()
    path = tmp_path / "runbook.md"

    write_runbook(plan, path)

    assert path.read_text(encoding="utf-8") == render_runbook(plan)


# -- Story 06 AC5: STALE banner via the render path ----------------------------


def test_render_runbook_default_drift_none_is_byte_identical_to_story_05() -> None:
    plan = make_migration_plan()

    assert render_runbook(plan) == render_runbook(plan, drift=None)
    assert "STALE" not in render_runbook(plan)


def test_render_runbook_no_drift_report_omits_stale_banner() -> None:
    plan = make_migration_plan()

    text = render_runbook(plan, drift=DriftReport())

    assert "STALE" not in text


def test_render_runbook_with_drift_renders_stale_banner_with_counts() -> None:
    plan = make_migration_plan()
    drift = DriftReport(
        source_added=("k1", "k2"),
        source_removed=("k3",),
        target_changed=("k4",),
    )

    text = render_runbook(plan, drift=drift)

    assert "## STALE -- drift detected since this plan's snapshots" in text
    assert "- source added: 2" in text
    assert "- source removed: 1" in text
    assert "- target changed: 1" in text
    assert "- source changed" not in text
    assert "- target added" not in text
    assert "- target removed" not in text


def test_render_runbook_stale_banner_renders_before_generated_at_header() -> None:
    plan = make_migration_plan()
    drift = DriftReport(source_added=("k1",))

    text = render_runbook(plan, drift=drift)

    title_idx = text.index("# Migration Runbook")
    stale_idx = text.index("## STALE")
    generated_idx = text.index("Generated-at")
    assert title_idx < stale_idx < generated_idx


def test_write_runbook_with_drift_writes_stale_banner_matching_render_runbook(
    tmp_path: Path,
) -> None:
    plan = make_migration_plan()
    drift = DriftReport(source_added=("k1",))
    path = tmp_path / "runbook.md"

    write_runbook(plan, path, drift=drift)

    text = path.read_text(encoding="utf-8")
    assert text == render_runbook(plan, drift=drift)
    assert "STALE" in text
