# src/nexus/cli/commands_migrate.py
# `nexus migrate select` subcommand.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Selective-migration-planner subcommands under the migrate group.

``select`` seeds a Selection YAML from an existing replatform checklist so a
consultant can curate include/exclude dispositions under git PR review
(ADR-026 Decision 2). Consumes a JSON-dumped ``MigrationChecklist`` rather
than recomputing one, keeping ``migrate/`` decoupled from live instance
access (ADR-026#Decision 1). The Typer command body is a thin wrapper over
``run_select``, mirroring ``commands_assess_replatform.py``'s
``run_inventory`` / ``run_migration`` pattern -- no ctx.obj, which would
clash with the RenderContext set by the root callback.
"""

import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from nexus.cli.apps import migrate_app
from nexus.cli.console import err_console
from nexus.cli.console import render_context as _render_context
from nexus.migrate.models import Selection, SelectionItem, emit_selection_yaml
from nexus.replatform.models import MigrationChecklist
from nexus.ui import Notice
from nexus.ui.render_context import RenderContext

__all__: list[str] = []


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
    except OSError as exc:
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
