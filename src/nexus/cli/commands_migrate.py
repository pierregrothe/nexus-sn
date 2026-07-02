# src/nexus/cli/commands_migrate.py
# `nexus migrate select` + `nexus migrate plan` subcommands.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Selective-migration-planner subcommands under the migrate group.

``select`` seeds a Selection YAML from an existing replatform checklist so a
consultant can curate include/exclude dispositions under git PR review
(ADR-026 Decision 2). Consumes a JSON-dumped ``MigrationChecklist`` rather
than recomputing one, keeping ``migrate/`` decoupled from live instance
access (ADR-026#Decision 1).

``plan`` (story 05) builds a ``MigrationPlan`` from a curated Selection --
closure (story 04) + waves (story 04) -- and renders its runbook (story
05a), also recording an instance-wide baseline listing on the plan (story
06). ``plan --recheck`` (story 06) re-inventories both instances and diffs
them against a plan's recorded baselines, marking the runbook STALE on
drift (ADR-026 Decision 4: freshness is enforced, not assumed) -- it never
writes to either instance and never touches the plan file itself (Must
Not: approval fields are only ever cleared by a human editing the plan
YAML). All three Typer command bodies are thin wrappers over
``run_select``/``run_plan``/``run_recheck``, mirroring
``commands_assess_replatform.py``'s ``run_inventory``/``run_migration``
pattern -- no ctx.obj, which would clash with the RenderContext set by the
root callback.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from nexus.capture.models import CaptureResult
from nexus.cli.apps import migrate_app
from nexus.cli.console import err_console
from nexus.cli.console import render_context as _render_context
from nexus.cli.migrate_wiring import (
    PlanCollaborators,
    RecheckCollaborators,
    default_plan_collaborators,
    default_recheck_collaborators,
)
from nexus.connectors.servicenow.errors import SNClientError
from nexus.migrate.closure import build_closure
from nexus.migrate.models import (
    BaselineEntry,
    DriftReport,
    MigrationPlan,
    Selection,
    SelectionItem,
    emit_plan_yaml,
    emit_selection_yaml,
    load_plan_yaml,
    load_selection_yaml,
)
from nexus.migrate.planner import build_waves, detect_cycles
from nexus.migrate.recheck import compute_drift, listing_from_entries, plan_has_baseline
from nexus.migrate.runbook import render_summary, write_runbook
from nexus.replatform.models import MigrationChecklist
from nexus.ui import Notice
from nexus.ui.render_context import RenderContext

__all__: list[str] = []

# MigrationPlan.schema_version stamped by `plan` -- bumping this is a
# schema-compatibility decision (ADR-026 Decision 5), not a per-run choice.
_PLAN_SCHEMA_VERSION = "1.0"


def _seed_selection(checklist: MigrationChecklist) -> Selection:
    """Seed one undecided SelectionItem per distinct checklist item key.

    Args:
        checklist: The replatform checklist to seed from.

    Returns:
        A Selection covering every distinct checklist item key exactly once
        (AC2), in the checklist's stable first-occurrence order, each
        carrying ``disposition="undecided"`` regardless of the checklist
        item's status -- v1 seeds everything undecided; curation is a later,
        human, git-reviewed step (AC3, ADR-026#Decision 2).
    """
    keys = dict.fromkeys(item.key for item in checklist.items)
    items = tuple(SelectionItem(key=key, disposition="undecided") for key in keys)
    return Selection(
        source_profile=checklist.source_profile,
        target_profile=checklist.target_profile,
        source_captured_at=checklist.source_captured_at,
        items=items,
    )


def run_select(
    *,
    checklist_path: Path,
    out: Path,
    render_context: RenderContext,
) -> int:
    """Seed a Selection YAML from a MigrationChecklist JSON file.

    Args:
        checklist_path: Path to a MigrationChecklist JSON file, the same
            shape ``MigrationChecklist.model_dump_json`` produces.
        out: Destination path for the seeded Selection YAML, written via the
            byte-stable ``emit_selection_yaml`` path (AC5).
        render_context: Destination console for the success summary.

    Returns:
        Exit code 0 on success; 1 when the checklist file is missing,
        unreadable, malformed JSON, or fails MigrationChecklist validation.
    """
    try:
        raw_text = checklist_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        err_console.print(Notice.error(f"cannot read checklist {checklist_path}: {exc}"))
        return 1
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        err_console.print(Notice.error(f"checklist {checklist_path} is not valid JSON: {exc}"))
        return 1
    try:
        checklist = MigrationChecklist.model_validate(data, strict=False)
    except ValidationError as exc:
        err_console.print(Notice.error(f"checklist {checklist_path} failed validation: {exc}"))
        return 1

    selection = _seed_selection(checklist)
    out.write_bytes(emit_selection_yaml(selection).encode("utf-8"))
    render_context.console.print(
        f"selection seeded: {len(selection.items)} item(s) -> {out}", highlight=False
    )
    return 0


@migrate_app.command("select")
def migrate_select(  # pragma: no cover -- thin Typer wrapper over run_select
    from_checklist: Annotated[
        str, typer.Option("--from-checklist", help="MigrationChecklist JSON file to seed from")
    ],
    out: Annotated[str, typer.Option("--out", help="Write the seeded Selection YAML to this path")],
) -> None:
    """Seed a Selection YAML from a replatform checklist for consultant curation."""
    code = run_select(
        checklist_path=Path(from_checklist),
        out=Path(out),
        render_context=_render_context,
    )
    raise typer.Exit(code)


def _latest_captured_at(captures: tuple[CaptureResult, ...], profile: str) -> datetime | None:
    """Return the latest captured_at among CaptureResults for ``profile``.

    Shared by the source and target sides of ``run_plan``'s MigrationPlan
    assembly: the plan must record the timestamps of the FRESH captures it
    was computed from (ADR-026 Decision 4), never the seed-time
    ``selection.source_captured_at`` carried forward from ``migrate select``.

    Args:
        captures: CaptureResults covering both instances.
        profile: Instance profile to filter on.

    Returns:
        The latest matching captured_at, or None when no CaptureResult in
        ``captures`` names ``profile``.
    """
    matches = [capture.captured_at for capture in captures if capture.instance_id == profile]
    return max(matches) if matches else None


def _sorted_baseline(entries: tuple[BaselineEntry, ...]) -> tuple[BaselineEntry, ...]:
    """Sort BaselineEntry rows by (key, fingerprint) for deterministic plan assembly.

    Args:
        entries: BaselineEntry rows from ``PlanCollaborators.build_baselines``.

    Returns:
        The same entries sorted by (key, fingerprint).
    """
    return tuple(sorted(entries, key=lambda entry: (entry.key, entry.fingerprint)))


def run_plan(
    *,
    selection_path: Path,
    out: Path,
    render_context: RenderContext,
    collaborators: PlanCollaborators,
) -> int:
    """Build a MigrationPlan from a curated Selection and render its runbook.

    The plan's ``source_captured_at``/``target_captured_at`` both come from
    the FRESH captures ``collaborators.build_captures`` just fetched -- never
    from ``selection.source_captured_at``, which is the seed-time value
    ``migrate select`` carried forward and may badly understate source
    currency (ADR-026 Decision 4: plans record what they were computed from).

    Args:
        selection_path: Path to a Selection YAML file (the
            ``emit_selection_yaml`` format ``migrate select`` produces).
        out: Destination for the runbook markdown. The plan YAML is written
            alongside it via the byte-stable ``emit_plan_yaml`` path, at
            ``out`` with its suffix replaced by ``.plan.yaml`` (e.g.
            ``runbook.md`` -> ``runbook.plan.yaml``).
        render_context: Destination console for the summary.
        collaborators: Injectable capture + schema-graph + baseline builders.
            The assembled plan's ``source_baseline``/``target_baseline``
            come from ``collaborators.build_baselines`` (story 06), sorted
            by (key, fingerprint) for determinism.

    Returns:
        Exit code 0 on success -- including a plan with unresolved blocking
        findings, since the runbook still renders and approval is a
        separate, later git-reviewed step (AC7). 1 when the selection file
        is missing/unreadable/malformed/invalid, a collaborator fails, or
        the captures do not cover either the source or the target profile.
    """
    try:
        raw_text = selection_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        err_console.print(Notice.error(f"cannot read selection {selection_path}: {exc}"))
        return 1
    try:
        selection = load_selection_yaml(raw_text)
    except ValidationError as exc:
        err_console.print(Notice.error(f"selection {selection_path} failed validation: {exc}"))
        return 1
    except ValueError as exc:
        err_console.print(Notice.error(f"selection {selection_path} is not valid YAML: {exc}"))
        return 1

    try:
        captures = collaborators.build_captures(selection)
        schema_graph = collaborators.build_schema_graph(selection)
        source_baseline, target_baseline = collaborators.build_baselines(selection)
    except SNClientError as exc:
        err_console.print(Notice.error(f"failed to capture instances for plan: {exc}"))
        return 1

    source_captured_at = _latest_captured_at(captures, selection.source_profile)
    if source_captured_at is None:
        err_console.print(
            Notice.error(
                f"no captured records found for source profile {selection.source_profile!r}"
            )
        )
        return 1
    target_captured_at = _latest_captured_at(captures, selection.target_profile)
    if target_captured_at is None:
        err_console.print(
            Notice.error(
                f"no captured records found for target profile {selection.target_profile!r}"
            )
        )
        return 1

    closure_result = build_closure(selection, captures, schema_graph)
    waves = build_waves(closure_result.items, closure_result.edges)
    cycle_findings = detect_cycles(closure_result.items, closure_result.edges)
    findings = tuple(
        sorted(
            (*closure_result.findings, *cycle_findings),
            key=lambda finding: (finding.kind, finding.subject_key, finding.detail),
        )
    )

    plan = MigrationPlan(
        schema_version=_PLAN_SCHEMA_VERSION,
        source_profile=selection.source_profile,
        target_profile=selection.target_profile,
        source_captured_at=source_captured_at,
        target_captured_at=target_captured_at,
        waves=waves,
        findings=findings,
        source_baseline=_sorted_baseline(source_baseline),
        target_baseline=_sorted_baseline(target_baseline),
    )

    plan_path = out.with_suffix(".plan.yaml")
    plan_path.write_bytes(emit_plan_yaml(plan).encode("utf-8"))
    render_summary(plan, render_context)
    write_runbook(plan, out)
    return 0


def _runbook_path_for_recheck(plan_path: Path, out_override: Path | None) -> Path | None:
    """Derive the runbook path a drifted recheck rewrites (AC5).

    Args:
        plan_path: The ``--plan`` path given to ``--recheck``.
        out_override: The ``--out`` path, if given.

    Returns:
        ``out_override`` when given; otherwise ``plan_path`` with its
        ``.plan.yaml`` suffix replaced by ``.md``; or None when
        ``plan_path`` does not end in ``.plan.yaml`` and no ``--out``
        override was given (the caller must error).
    """
    if out_override is not None:
        return out_override
    name = plan_path.name
    if not name.endswith(".plan.yaml"):
        return None
    return plan_path.with_name(name[: -len(".plan.yaml")] + ".md")


def _render_drift_report(drift: DriftReport, render_context: RenderContext) -> None:
    """Print the drift report grouped by instance and change kind (AC2).

    Args:
        drift: The computed DriftReport.
        render_context: Destination console.
    """
    groups = (
        ("source", "added", drift.source_added),
        ("source", "removed", drift.source_removed),
        ("source", "changed", drift.source_changed),
        ("target", "added", drift.target_added),
        ("target", "removed", drift.target_removed),
        ("target", "changed", drift.target_changed),
    )
    for instance, kind, keys in groups:
        if not keys:
            continue
        render_context.console.print(f"{instance} {kind} ({len(keys)}):", highlight=False)
        for key in keys:
            render_context.console.print(f"  {key}", highlight=False)


def run_recheck(
    *,
    plan_path: Path,
    out_override: Path | None,
    render_context: RenderContext,
    collaborators: RecheckCollaborators,
) -> int:
    """Re-inventory both instances and report drift against a plan's baselines.

    Read-only: never writes to either ServiceNow instance, and never
    rewrites ``plan_path`` itself -- the plan's approval block
    (``approved_by``/``approved_at``) is only ever cleared by a human
    editing the plan YAML (Must Not).

    Args:
        plan_path: Path to a MigrationPlan YAML file (the ``emit_plan_yaml``
            format ``migrate plan`` produces).
        out_override: Optional ``--out`` override for the runbook rewrite
            path on drift; required when ``plan_path`` does not end in
            ``.plan.yaml``.
        render_context: Destination console for the drift report.
        collaborators: Injectable fresh-listing builder.

    Returns:
        Exit code 0 when no drift is detected (AC1); 2 when drift is
        detected (AC2); 1 when the plan is missing/unreadable/malformed/
        invalid, has no usable baseline, a collaborator fails (e.g. an
        instance is unreachable), or a drifted recheck cannot determine a
        runbook path to rewrite (AC3).
    """
    try:
        raw_text = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        err_console.print(Notice.error(f"cannot read plan {plan_path}: {exc}"))
        return 1
    try:
        plan = load_plan_yaml(raw_text)
    except ValidationError as exc:
        err_console.print(Notice.error(f"plan {plan_path} failed validation: {exc}"))
        return 1
    except ValueError as exc:
        err_console.print(Notice.error(f"plan {plan_path} is not valid YAML: {exc}"))
        return 1

    if not plan_has_baseline(plan):
        err_console.print(
            Notice.error(
                f"plan {plan_path} has no recheck baseline -- regenerate it with "
                "`nexus migrate plan` on this version to enable --recheck"
            )
        )
        return 1

    try:
        source_entries, target_entries = collaborators.build_listings(
            plan.source_profile, plan.target_profile
        )
    except SNClientError as exc:
        err_console.print(Notice.error(f"failed to re-inventory instances for recheck: {exc}"))
        return 1
    drift = compute_drift(
        plan, listing_from_entries(source_entries), listing_from_entries(target_entries)
    )

    if not drift.has_drift:
        render_context.console.print("no drift detected", highlight=False)
        return 0

    _render_drift_report(drift, render_context)
    runbook_path = _runbook_path_for_recheck(plan_path, out_override)
    if runbook_path is None:
        err_console.print(
            Notice.error(
                f"plan {plan_path} does not end in .plan.yaml -- pass --out to say "
                "where the STALE runbook should be rewritten"
            )
        )
        return 1
    write_runbook(plan, runbook_path, drift=drift)
    return 2


@migrate_app.command("plan")
def migrate_plan(  # pragma: no cover -- thin Typer wrapper over run_plan/run_recheck
    selection: Annotated[
        str, typer.Option("--selection", help="Selection YAML to build a MigrationPlan from")
    ] = "",
    out: Annotated[
        str,
        typer.Option(
            "--out",
            help=(
                "Write the runbook markdown to this path; the plan YAML is written "
                "alongside it, at --out with its suffix replaced by .plan.yaml. With "
                "--recheck, only needed when --plan does not end in .plan.yaml -- "
                "overrides the derived runbook rewrite path on drift"
            ),
        ),
    ] = "",
    recheck: Annotated[
        bool,
        typer.Option(
            "--recheck",
            help="Re-inventory both instances and report drift against --plan's baselines",
        ),
    ] = False,
    plan: Annotated[
        str,
        typer.Option(
            "--plan", help="MigrationPlan YAML to recheck drift against (required with --recheck)"
        ),
    ] = "",
) -> None:
    """Build a MigrationPlan from a curated Selection and render its runbook, or --recheck drift."""
    if recheck:
        if not plan:
            err_console.print(Notice.error("--recheck requires --plan"))
            raise typer.Exit(1)
        code = run_recheck(
            plan_path=Path(plan),
            out_override=Path(out) if out else None,
            render_context=_render_context,
            collaborators=default_recheck_collaborators(),
        )
        raise typer.Exit(code)

    if not selection:
        err_console.print(Notice.error("--selection is required"))
        raise typer.Exit(1)
    if not out:
        err_console.print(Notice.error("--out is required"))
        raise typer.Exit(1)
    code = run_plan(
        selection_path=Path(selection),
        out=Path(out),
        render_context=_render_context,
        collaborators=default_plan_collaborators(),
    )
    raise typer.Exit(code)
