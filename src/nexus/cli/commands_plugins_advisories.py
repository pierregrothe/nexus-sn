# src/nexus/cli/commands_plugins_advisories.py
# Typer commands for advisory listing and deferral (advisories, defer, undo-defer, list-deferred).
# Author: Pierre Grothe
# Date: 2026-05-16
"""`nexus plugins` advisory commands.

Extracted from ``commands_plugins_analysis.py`` per ADR-023 (file-size
cap). Owns the four advisory-management commands: ``advisories`` listing
plus the ``defer / undo-defer / list-deferred`` override lifecycle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Annotated

import typer

from nexus.cli.apps import plugins_app
from nexus.cli.console import console, err_console
from nexus.cli.formats import _emit_json, _validate_format
from nexus.cli.renderables import (
    ADVISORY_COLUMNS,
    SEVERITY_ORDER,
    advisory_detail_panel,
    build_advisory_rows,
    build_advisory_summary,
    severity_at_or_above,
)
from nexus.cli.utils import today as _today
from nexus.cli.utils import trunc as _trunc
from nexus.cli.views import (
    _emit_framed_view,
    _load_inventory_or_exit,
    _plugins_expandable_renderables,
    _plugins_header_renderables,
)
from nexus.config.paths import NexusPaths
from nexus.instances.registry import InstanceRegistry
from nexus.plugins.advisories import AdvisoryDatabase, compute_advisories
from nexus.plugins.errors import PluginAdvisoryDataError
from nexus.plugins.models import AdvisoryType, Severity
from nexus.plugins.overrides import AdvisoryOverride, AdvisoryOverrideSet, apply_overrides
from nexus.ui import DataColumn, DataTable, Notice

if TYPE_CHECKING:
    from rich.console import RenderableType

    from nexus.ui.components.framed_viewer import DetailsType


__all__: list[str] = []


@plugins_app.command("advisories")
def plugins_advisories(
    ctx: typer.Context,
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    advisory_type: Annotated[
        str,
        typer.Option(
            "--type",
            help="Filter to one advisory type: eol, cve, or license.",
        ),
    ] = "",
    severity: Annotated[
        str,
        typer.Option(
            "--severity",
            help="Show only findings at or above this severity (critical|high|medium|low).",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit with code 1 if any findings remain after filters.",
        ),
    ] = False,
    include_deferred: Annotated[
        bool,
        typer.Option(
            "--include-deferred",
            help="Include deferred findings in output (marked [deferred]).",
        ),
    ] = False,
) -> None:
    """Show EOL / CVE / license findings for plugins on an instance."""
    _validate_format(output_format)
    meta, inventory = _load_inventory_or_exit(instance)
    try:
        db = AdvisoryDatabase.load()
    except PluginAdvisoryDataError as exc:
        console.print(Notice.error(f"Advisory data corrupted: {exc}"))
        raise typer.Exit(1) from exc

    today = _today()
    result = compute_advisories(inventory, db, today=today)

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    overrides_set = registry.load_advisory_overrides(meta.profile)
    remaining_set, deferred = apply_overrides(result, overrides_set)
    deferred_count = len(deferred)
    findings = remaining_set.findings

    if include_deferred:
        marked_deferred = tuple(
            f.model_copy(
                update={
                    "summary": f"[deferred] {f.summary}",
                    "details": f"[deferred] {f.details}",
                }
            )
            for f in deferred
        )
        sev_index: dict[Severity, int] = {s: i for i, s in enumerate(SEVERITY_ORDER)}
        findings = tuple(
            sorted(
                (*findings, *marked_deferred),
                key=lambda f: (sev_index[f.severity], f.plugin_id),
            )
        )

    if advisory_type:
        try:
            wanted_type = AdvisoryType(advisory_type)
        except ValueError as exc:
            console.print(Notice.error(f"Unknown --type: {advisory_type}"))
            raise typer.Exit(1) from exc
        findings = tuple(f for f in findings if f.advisory_type is wanted_type)

    if severity:
        try:
            floor = Severity(severity)
        except ValueError as exc:
            console.print(Notice.error(f"Unknown --severity: {severity}"))
            raise typer.Exit(1) from exc
        keep = severity_at_or_above(floor)
        findings = tuple(f for f in findings if f.severity in keep)

    if output_format == "json":
        _emit_json(result.model_copy(update={"findings": findings}))
        if strict and findings:
            raise typer.Exit(1)
        return

    if not findings and not deferred_count:
        console.print(Notice.info("No advisories found."))
        return

    summary = build_advisory_summary(findings, deferred_count=deferred_count)
    advisory_details: DetailsType = tuple(advisory_detail_panel(f) for f in findings)
    _emit_framed_view(
        ctx,
        header_renderables=_plugins_header_renderables(),
        expandable_renderables=_plugins_expandable_renderables(),
        title=f"Advisories -- {meta.profile}",
        columns=ADVISORY_COLUMNS,
        rows=build_advisory_rows(findings),
        row_details=advisory_details,
        footer_renderables=(summary,),
    )
    if strict and findings:
        raise typer.Exit(1)


@plugins_app.command("defer")
def plugins_advisories_defer(
    plugin_id: Annotated[str, typer.Argument(help="SN plugin identifier")],
    advisory_type: Annotated[str, typer.Argument(help="eol | cve | license")],
    details: Annotated[str, typer.Argument(help="Exact finding details string")],
    reason: Annotated[str, typer.Option("--reason", help="Required justification")] = "",
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Defer an EOL/CVE/license advisory finding on a plugin."""
    if not plugin_id or not advisory_type or not details or not reason:
        err_console.print(
            Notice.error("Missing required: PLUGIN_ID, ADVISORY_TYPE, DETAILS, --reason")
        )
        raise typer.Exit(2)
    try:
        wanted_type = AdvisoryType(advisory_type)
    except ValueError as exc:
        console.print(Notice.error(f"Unknown advisory type: {advisory_type}"))
        raise typer.Exit(1) from exc
    if not reason.strip():
        console.print(Notice.error("--reason must not be empty"))
        raise typer.Exit(1)

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, inventory = _load_inventory_or_exit(instance)
    try:
        db = AdvisoryDatabase.load()
    except PluginAdvisoryDataError as exc:
        console.print(Notice.error(f"Advisory data corrupted: {exc}"))
        raise typer.Exit(1) from exc
    today = _today()
    advisories = compute_advisories(inventory, db, today=today)

    if not any(
        f.plugin_id == plugin_id and f.advisory_type is wanted_type and f.details == details
        for f in advisories.findings
    ):
        console.print(
            Notice.error(
                f"No matching finding for plugin={plugin_id} type={wanted_type.value} "
                f"details={details!r}"
            )
        )
        raise typer.Exit(1)

    existing = registry.load_advisory_overrides(meta.profile)
    if any(
        o.plugin_id == plugin_id and o.advisory_type is wanted_type and o.details == details
        for o in existing.overrides
    ):
        console.print(Notice.error("Override already exists for that finding"))
        raise typer.Exit(1)

    new_override = AdvisoryOverride(
        plugin_id=plugin_id,
        advisory_type=wanted_type,
        details=details,
        reason=reason,
        created_at=datetime.now(UTC),
    )
    combined = tuple(
        sorted(
            (*existing.overrides, new_override),
            key=lambda o: (o.plugin_id, o.advisory_type.value, o.details),
        )
    )
    registry.save_advisory_overrides(meta.profile, AdvisoryOverrideSet(overrides=combined))
    console.print(Notice.info(f"Deferred {wanted_type.value} {details} on {plugin_id}"))


@plugins_app.command("undo-defer")
def plugins_advisories_undo_defer(
    plugin_id: Annotated[str, typer.Argument(help="SN plugin identifier")],
    advisory_type: Annotated[str, typer.Argument(help="eol | cve | license")],
    details: Annotated[str, typer.Argument(help="Exact finding details string")],
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Remove a previously deferred advisory finding."""
    try:
        wanted_type = AdvisoryType(advisory_type)
    except ValueError as exc:
        console.print(Notice.error(f"Unknown advisory type: {advisory_type}"))
        raise typer.Exit(1) from exc

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    existing = registry.load_advisory_overrides(meta.profile)
    filtered = tuple(
        o
        for o in existing.overrides
        if not (
            o.plugin_id == plugin_id and o.advisory_type is wanted_type and o.details == details
        )
    )
    if len(filtered) == len(existing.overrides):
        console.print(Notice.error("No matching override found"))
        raise typer.Exit(1)
    registry.save_advisory_overrides(meta.profile, AdvisoryOverrideSet(overrides=filtered))
    console.print(Notice.info(f"Removed override for {wanted_type.value} {details} on {plugin_id}"))


@plugins_app.command("list-deferred")
def plugins_advisories_list_deferred(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """List all deferred advisory findings for an instance."""
    _validate_format(output_format)
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    overrides_set = registry.load_advisory_overrides(meta.profile)

    if output_format == "json":
        _emit_json(overrides_set)
        return
    if not overrides_set.overrides:
        console.print(Notice.info("No advisory overrides."))
        return

    rows: list[list[RenderableType]] = [
        [
            o.plugin_id,
            o.advisory_type.value,
            _trunc(o.details, 30),
            _trunc(o.reason, 40),
            str(o.created_at.date()),
        ]
        for o in overrides_set.overrides
    ]
    console.print(
        DataTable(
            title=f"Deferred advisories -- {meta.profile}",
            columns=[
                DataColumn(header="Plugin", width=28),
                DataColumn(header="Type", width=8),
                DataColumn(header="Details", width=30),
                DataColumn(header="Reason", width=40),
                DataColumn(header="Created", width=12),
            ],
            rows=rows,
        )
    )
