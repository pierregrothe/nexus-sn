# src/nexus/cli/commands_capture.py
# Typer command bodies for the `nexus capture` sub-app.
# Author: Pierre Grothe
# Date: 2026-05-16
"""`nexus capture` Typer commands.

Extracted from ``cli/__init__.py`` per ADR-023. The capture sub-app
manages local archives of scope-scoped AI/automation configurations
captured from a ServiceNow instance.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
import yaml as _yaml

from nexus.capture.models import ArchiveManifest, ScopeEntry
from nexus.capture.tables import AI_AUTOMATION, DEFAULT_TABLE_GROUPS
from nexus.cli.apps import capture_app
from nexus.cli.auth import config_default as _config_default
from nexus.cli.console import console, err_console
from nexus.cli.utils import trunc as _trunc
from nexus.cli.views import (
    _build_capture_engine,
    _capture_expandable_renderables,
    _capture_header_renderables,
    _emit_framed_view,
)
from nexus.config.paths import NexusPaths
from nexus.ui import DataColumn, DataTable, Hint, KeyValuePanel, KvRow, Notice, nexus_progress

if TYPE_CHECKING:
    from rich.console import RenderableType

    from nexus.connectors.servicenow.client import ServiceNowClient
    from nexus.ui.components.framed_viewer import DetailsType

from nexus.cli.renderables import scope_detail_panel

__all__: list[str] = []


_CUSTOM_SCOPE_PREFIXES = ("x_", "u_")
_SCOPE_KEY_WIDTH = 26
_SCOPE_NAME_WIDTH = 20

# Short column header per table spec name -- wide enough to be readable, narrow to fit 80-col
_TABLE_HEADER: dict[str, str] = {
    "ai_skill": "Skl",
    "sys_hub_flow": "Flow",
    "sys_hub_action_type_definition": "Act",
    "virtual_agent_conversation_topic": "VA",
    "sys_ai_agent": "AI",
}

_UUID_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


@capture_app.callback(invoke_without_command=True)
def capture_callback(ctx: typer.Context) -> None:
    """Show local archives and available commands."""
    if ctx.invoked_subcommand is not None:
        return
    for renderable in _capture_header_renderables():
        console.print(renderable)


@capture_app.command("discover")
def capture_discover(
    ctx: typer.Context,
    instance: Annotated[
        str, typer.Argument(help="Instance profile name (default: configured default)")
    ] = "",
    group: Annotated[str, typer.Option(help="Table group")] = AI_AUTOMATION.key,
    all_scopes: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Show all scopes, not just your custom ones (x_*, u_*)",
        ),
    ] = False,
) -> None:
    """Discover which of your scopes have custom AI/automation configs."""

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        resolved = instance or _config_default()

        with nexus_progress(console) as progress:
            task = progress.add_task(f"Connecting to {resolved}...", total=None)

            def on_progress(completed: int, total: int, message: str) -> None:
                progress.update(
                    task,
                    description=message,
                    total=total if total > 0 else None,
                    completed=completed,
                )

            async with client:
                manifest = await engine.discover_scopes(resolved, group, on_progress=on_progress)

        if not manifest.scopes:
            console.print(Notice.info(f"No scopes with custom configurations found on {resolved}."))
            return

        all_s = list(manifest.scopes)
        custom_s = [s for s in all_s if s.scope.startswith(_CUSTOM_SCOPE_PREFIXES)]

        def _total(s: ScopeEntry) -> int:
            return sum(s.table_counts.values())

        custom_s.sort(key=_total, reverse=True)
        display = all_s if all_scopes else (custom_s if custom_s else all_s)

        group_obj = DEFAULT_TABLE_GROUPS.get(group)
        columns: list[DataColumn] = [
            DataColumn(header="Scope Key", width=_SCOPE_KEY_WIDTH),
            DataColumn(header="Name", width=_SCOPE_NAME_WIDTH),
        ]
        if group_obj:
            for spec in group_obj.tables:
                hdr = _TABLE_HEADER.get(spec.name, spec.display[:4])
                columns.append(DataColumn(header=hdr, width=5, justify="right"))

        rows: list[list[RenderableType]] = []
        for scope in display:
            row: list[RenderableType] = [
                _trunc(scope.scope, _SCOPE_KEY_WIDTH),
                _trunc(scope.name, _SCOPE_NAME_WIDTH),
            ]
            if group_obj:
                for spec in group_obj.tables:
                    row.append(str(scope.table_counts.get(spec.name, 0)))
            rows.append(row)

        if all_scopes or not custom_s:
            summary = f"{len(display)} scopes with custom configs on {resolved}"
        else:
            summary = (
                f"Showing {len(custom_s)} of your custom scopes "
                f"({len(all_s)} total with configs). Use --all to show all."
            )
        scope_details: DetailsType = tuple(scope_detail_panel(s) for s in display)
        _emit_framed_view(
            ctx,
            header_renderables=_capture_header_renderables(),
            expandable_renderables=_capture_expandable_renderables(),
            title=f"Custom scopes on {resolved}",
            columns=tuple(columns),
            rows=tuple(tuple(row) for row in rows),
            row_details=scope_details,
            footer_renderables=(Notice.info(summary),),
        )

        if display:
            example = display[0].scope
            console.print()
            console.print(Hint(label="Next", command=f"nexus capture pull --scope {example}"))
            if len(display) > 1:
                console.print(
                    Hint(
                        label="Tip",
                        command="--scope x_a --scope x_b",
                        suffix="captures multiple at once",
                    )
                )

    asyncio.run(_run())


async def _resolve_scope_ids(
    scope_args: list[str],
    client: ServiceNowClient,
) -> list[str]:
    """Resolve scope keys (x_snc_*) or sys_ids to sys_ids.

    UUID args are passed through unchanged. Scope keys are resolved with a
    single direct sys_scope lookup instead of a full grouped-count discover.

    Args:
        scope_args: List of scope keys or sys_ids from --scope options.
        client: Open ServiceNowClient to use for key lookups.

    Returns:
        List of resolved sys_ids in the same order as scope_args.
    """
    keys_to_lookup = [s for s in scope_args if not _UUID_RE.match(s.replace("-", ""))]

    if not keys_to_lookup:
        return scope_args

    in_query = f"scopeIN{','.join(keys_to_lookup)}"
    rows = await client.list_records(
        "sys_scope",
        query=in_query,
        fields="sys_id,scope",
        limit=len(keys_to_lookup) + 1,
    )
    key_map = {str(r.get("scope", "")): str(r.get("sys_id", "")) for r in rows}

    resolved: list[str] = []
    for arg in scope_args:
        if _UUID_RE.match(arg.replace("-", "")):
            resolved.append(arg)
        elif arg in key_map:
            resolved.append(key_map[arg])
            console.print(Notice.info(f"Resolved {arg} -> {key_map[arg]}"))
        else:
            err_console.print(
                Notice.error(
                    f"Scope {arg!r} not found. "
                    f"Run 'nexus capture discover' to see available scopes."
                )
            )
            raise typer.Exit(1)
    return resolved


@capture_app.command("pull")
def capture_pull(
    instance: Annotated[
        str, typer.Argument(help="Instance profile name (default: configured default)")
    ] = "",
    scope: Annotated[
        list[str],
        typer.Option(help="Scope key (e.g. x_snc_my_app) or sys_id -- repeatable, from 'discover'"),
    ] = [],
    group: Annotated[str, typer.Option(help="Table group")] = AI_AUTOMATION.key,
) -> None:
    """Capture custom configurations for one or more scopes to a local archive.

    Run 'nexus capture discover' first to see scope keys.
    """
    if not scope:
        err_console.print("At least one --scope is required.")
        err_console.print("  Run 'nexus capture discover' to see your scope keys.")
        raise typer.Exit(1)

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        resolved_instance = instance or _config_default()

        async with client:
            scope_ids = await _resolve_scope_ids(scope, client)

            with nexus_progress(console) as progress:
                task = progress.add_task("Preparing...", total=None)

                def on_progress(completed: int, total: int, message: str) -> None:
                    progress.update(
                        task,
                        description=message,
                        total=total if total > 0 else None,
                        completed=completed,
                    )

                result = await engine.capture(
                    resolved_instance, scope_ids, group, on_progress=on_progress
                )

        manifest = engine.save_archive(result)
        console.print(
            KeyValuePanel(
                title="Capture complete",
                rows=[
                    KvRow(label="Records", value=f"{manifest.record_count:,}"),
                    KvRow(label="Archive", value=str(manifest.archive_dir)),
                    KvRow(
                        label="Next",
                        value=f"nexus capture push {manifest.archive_dir}",
                    ),
                ],
            )
        )

    asyncio.run(_run())


@capture_app.command("list")
def capture_list(
    instance: Annotated[str | None, typer.Argument(help="Filter by instance")] = None,
) -> None:
    """List local capture archives."""
    archives_root = NexusPaths.from_env().archives_dir
    if not archives_root.exists():
        console.print(
            Hint(label="No archives yet", command="nexus capture pull", suffix="to capture one")
        )
        return

    rows: list[list[RenderableType]] = []
    for manifest_path in sorted(archives_root.rglob("manifest.yaml")):
        try:
            raw = _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest = ArchiveManifest.model_validate(raw, strict=False)
        except Exception as exc:
            err_console.print(
                Notice.warn(f"Skipping corrupt manifest {manifest_path.parent}: {exc}")
            )
            continue
        if instance and manifest.instance_id != instance:
            continue
        rows.append(
            [
                manifest.instance_id,
                str(manifest.captured_at)[:19],
                str(manifest.record_count),
                _trunc(str(manifest.archive_dir), 45),
            ]
        )
    console.print(
        DataTable(
            title="Archives",
            columns=[
                DataColumn(header="Instance", width=12),
                DataColumn(header="Captured", width=20),
                DataColumn(header="Recs", width=6, justify="right"),
                DataColumn(header="Archive"),
            ],
            rows=rows,
        )
    )


@capture_app.command("push")
def capture_push(
    archive: Annotated[str, typer.Argument(help="Path to archive directory")],
    instance: Annotated[
        str, typer.Argument(help="Target instance profile (default: configured default)")
    ] = "",
    update_set: Annotated[str, typer.Option(help="Update set name")] = "NEXUS-capture",
) -> None:
    """Push a local archive into an update set on the target instance."""

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        manifest_path = Path(archive) / "manifest.yaml"
        result = engine.load_archive(manifest_path)
        resolved_instance = instance or _config_default()
        async with client:
            ref = await engine.push_to_update_set(result, resolved_instance, update_set)
        console.print(
            KeyValuePanel(
                title="Push complete",
                rows=[
                    KvRow(label="Records", value=str(ref.record_count)),
                    KvRow(label="Update set", value=ref.name),
                    KvRow(label="sys_id", value=ref.sys_id),
                ],
            )
        )

    asyncio.run(_run())
