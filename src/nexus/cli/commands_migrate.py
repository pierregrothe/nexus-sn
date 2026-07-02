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
05a). Both Typer command bodies are thin wrappers over ``run_select`` /
``run_plan``, mirroring ``commands_assess_replatform.py``'s
``run_inventory`` / ``run_migration`` pattern -- no ctx.obj, which would
clash with the RenderContext set by the root callback.
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
from nexus.cli.migrate_wiring import PlanCollaborators, default_plan_collaborators
from nexus.connectors.servicenow.errors import SNClientError
from nexus.migrate.closure import build_closure
from nexus.migrate.models import (
    MigrationPlan,
    Selection,
    SelectionItem,
    emit_plan_yaml,
    emit_selection_yaml,
    load_selection_yaml,
)
from nexus.migrate.planner import build_waves, detect_cycles
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
        collaborators: Injectable capture + schema-graph builders.

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
    )

    plan_path = out.with_suffix(".plan.yaml")
    plan_path.write_bytes(emit_plan_yaml(plan).encode("utf-8"))
    render_summary(plan, render_context)
    write_runbook(plan, out)
    return 0


@migrate_app.command("plan")
def migrate_plan(  # pragma: no cover -- thin Typer wrapper over run_plan
    selection: Annotated[
        str, typer.Option("--selection", help="Selection YAML to build a MigrationPlan from")
    ],
    out: Annotated[
        str,
        typer.Option(
            "--out",
            help=(
                "Write the runbook markdown to this path; the plan YAML is written "
                "alongside it, at --out with its suffix replaced by .plan.yaml"
            ),
        ),
    ],
) -> None:
    """Build a MigrationPlan from a curated Selection and render its runbook."""
    code = run_plan(
        selection_path=Path(selection),
        out=Path(out),
        render_context=_render_context,
        collaborators=default_plan_collaborators(),
    )
    raise typer.Exit(code)
