# src/nexus/cli/commands_plugins_analysis.py
# Typer commands for plugin analysis (advisories, impact, orphans, drift, recommend, baselines).
# Author: Pierre Grothe
# Date: 2026-05-16
"""`nexus plugins` analysis commands.

Extracted from ``cli/__init__.py`` per ADR-023. Read-mostly commands that
compute analytical reports (EOL/CVE/license findings, reverse-dep
impact, orphan candidates, drift, AI explanations) plus the
``recommend`` and ``baselines`` sub-apps.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated

import httpx
import typer

from nexus.api.errors import AnthropicError
from nexus.cli.apps import baselines_app, plugins_app, recommend_app
from nexus.cli.auth import acquire_token as _acquire_token
from nexus.cli.console import console, err_console
from nexus.cli.formats import _emit_json, _OrphansReport, _validate_format
from nexus.cli.help_text import (
    PLUGINS_BASELINES_HELP,
    PLUGINS_BASELINES_PARENT,
    PLUGINS_RECOMMEND_HELP,
    PLUGINS_RECOMMEND_PARENT,
    guide_items,
)
from nexus.cli.renderables import (
    drift_detail_panel,
    drift_row,
    plugin_detail_panel,
    status_breakdown,
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
from nexus.plugins.baselines import DEFAULT_BASELINE_NAME, validate_baseline_name
from nexus.plugins.drift import compute_drift
from nexus.plugins.errors import (
    BaselineNotFoundError,
    InvalidBaselineNameError,
    PluginImpactError,
)
from nexus.plugins.impact import compute_impact
from nexus.plugins.models import PluginImpact
from nexus.plugins.orphans import orphan_candidates
from nexus.plugins.recommendations import (
    AI_MODEL,
    DEACTIVATE_SYSTEM_PROMPT,
    EXPLAIN_SYSTEM_PROMPT,
    ROADMAP_SYSTEM_PROMPT,
    build_deactivation_context,
    build_explain_context,
    build_roadmap_context,
)
from nexus.ui import CommandGuide, CommandHelp, DataColumn, DataTable, Hint, Notice

if TYPE_CHECKING:
    from rich.console import RenderableType

    from nexus.api.agent_client import AgentClientProtocol
    from nexus.ui.components.framed_viewer import DetailsType, RowsType


__all__: list[str] = []


def _impact_transport() -> httpx.AsyncBaseTransport | None:
    """Return the async transport used by the impact command.

    In production this returns ``None`` so httpx uses the real network.
    Tests monkeypatch this to inject an ``httpx.MockTransport``.
    """
    return None


def _agent_client_factory() -> AgentClientProtocol:
    """Return a real AgentClient; monkeypatched in tests.

    Returns:
        AgentClient instance for LLM calls.
    """
    from nexus.api.agent_client import AgentClient  # noqa: PLC0415

    return AgentClient()


@plugins_app.command("impact")
def plugins_impact(
    plugin_id: Annotated[
        str,
        typer.Argument(help="Plugin identifier (e.g. com.acme.helper)"),
    ] = "",
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
    live: Annotated[
        bool,
        typer.Option(
            "--live",
            help="Force a live re-query of SN record counts instead of using the cached breakdown.",
        ),
    ] = False,
    no_cross_scope: Annotated[
        bool,
        typer.Option(
            "--no-cross-scope",
            help="Skip the cross-scope FK reference scan.",
        ),
    ] = False,
) -> None:
    """Show reverse dependencies + scope-owned record counts for a plugin."""
    _validate_format(output_format)
    _, inventory = _load_inventory_or_exit(instance)
    _registry, meta, token, _expiry = _acquire_token(instance)
    transport = _impact_transport()
    try:
        impact = asyncio.run(
            compute_impact(
                inventory,
                plugin_id,
                url=meta.url,
                token=token,
                transport=transport,
                live=live,
                cross_scope=not no_cross_scope,
            )
        )
    except PluginImpactError as exc:
        console.print(Notice.error(f"Plugin not found: {plugin_id}"))
        raise typer.Exit(1) from exc

    if output_format == "json":
        _emit_json(impact)
        return
    _render_impact(impact, opted_out=no_cross_scope)


def _render_impact(impact: PluginImpact, *, opted_out: bool = False) -> None:
    """Render the impact DataTables + trailing summary Notice.

    Args:
        impact: PluginImpact from compute_impact.
        opted_out: True when the user passed --no-cross-scope; suppresses
            the unavailability warning for the cross-scope section.
    """
    if impact.reverse_deps:
        dep_rows: list[list[RenderableType]] = [
            [
                d.plugin_id,
                d.name,
                d.state,
                str(d.depth),
                _trunc("->".join(d.via), 60),
            ]
            for d in impact.reverse_deps
        ]
        console.print(
            DataTable(
                title="Reverse dependencies",
                columns=[
                    DataColumn(header="Plugin ID", width=32),
                    DataColumn(header="Name", width=20),
                    DataColumn(header="State", width=10),
                    DataColumn(header="Depth", width=7),
                    DataColumn(header="Via", width=60),
                ],
                rows=dep_rows,
            )
        )
    else:
        console.print(Notice.info(f"No plugins depend on {impact.target_plugin_id}."))

    total_records = 0
    if not impact.counts_available:
        console.print(Notice.warn("Record counts unavailable -- could not reach instance."))
    elif not impact.record_counts:
        console.print(Notice.info("No scope-owned records."))
    else:
        count_rows: list[list[RenderableType]] = [
            [c.table, f"{c.count:,}"] for c in impact.record_counts
        ]
        console.print(
            DataTable(
                title="Scope-owned records",
                columns=[
                    DataColumn(header="Table", width=32),
                    DataColumn(header="Count", width=12),
                ],
                rows=count_rows,
            )
        )
        total_records = sum(c.count for c in impact.record_counts)

    if opted_out:
        console.print(Notice.info("Cross-scope scan skipped (--no-cross-scope)."))
    elif not impact.cross_scope_available:
        console.print(
            Notice.warn(
                "Cross-scope scan unavailable -- the SN aggregate API errored "
                "(likely permissions or async-pending). See logs for detail."
            )
        )
    elif not impact.cross_scope_refs:
        console.print(Notice.info("No inbound cross-scope references."))
    if impact.cross_scope_available and impact.cross_scope_refs:
        ref_rows: list[list[RenderableType]] = [
            [
                r.source_scope,
                r.source_table,
                r.field,
                r.target_table,
                f"{r.record_count:,}",
            ]
            for r in impact.cross_scope_refs
        ]
        console.print(
            DataTable(
                title="Cross-scope references",
                columns=[
                    DataColumn(header="Source scope", width=24),
                    DataColumn(header="Source table", width=24),
                    DataColumn(header="Field", width=16),
                    DataColumn(header="Target table", width=20),
                    DataColumn(header="Records", width=10),
                ],
                rows=ref_rows,
            )
        )

    cross_scope_suffix = (
        f"; {len(impact.cross_scope_refs)} cross-scope refs" if impact.cross_scope_refs else ""
    )
    if impact.counts_available:
        console.print(
            Notice.info(
                f"{len(impact.reverse_deps)} dependent plugin(s); "
                f"{total_records:,} records in scope {impact.target_plugin_id}"
                f"{cross_scope_suffix}."
            )
        )
    else:
        console.print(
            Notice.info(f"{len(impact.reverse_deps)} dependent plugin(s){cross_scope_suffix}.")
        )


_ORPHAN_STATES = ("active", "inactive")


@plugins_app.command("orphans")
def plugins_orphans(
    ctx: typer.Context,
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    state: Annotated[
        str,
        typer.Option(
            "--state",
            help="Filter to one plugin state: active or inactive.",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """Show plugins with no dependents AND no scope-owned records."""
    _validate_format(output_format)
    meta, inventory = _load_inventory_or_exit(instance)
    if all(p.record_counts is None for p in inventory.plugins):
        console.print(
            Notice.warn("Inventory has no record counts -- run nexus instance refresh to populate.")
        )
        console.print(Hint(label="Refresh", command=f"nexus instance refresh {meta.profile}"))
        raise typer.Exit(1)
    if state and state not in _ORPHAN_STATES:
        console.print(Notice.error(f"Unknown --state: {state}"))
        raise typer.Exit(1)
    candidates = orphan_candidates(inventory)
    if state:
        candidates = tuple(p for p in candidates if p.state == state)
    if output_format == "json":
        _emit_json(_OrphansReport(candidates=tuple(candidates)))
        return
    if not candidates:
        console.print(Notice.info("No orphan candidates."))
        return
    orphan_rows: RowsType = tuple(
        (
            p.plugin_id,
            p.name,
            "active" if p.state == "active" else "inactive (license slot)",
            "no records",
        )
        for p in candidates
    )
    orphan_details: DetailsType = tuple(plugin_detail_panel(p) for p in candidates)
    _emit_framed_view(
        ctx,
        header_renderables=_plugins_header_renderables(),
        expandable_renderables=_plugins_expandable_renderables(),
        title=f"Orphan candidates -- {meta.profile}",
        columns=(
            DataColumn(header="Plugin ID", width=32),
            DataColumn(header="Name", width=24),
            DataColumn(header="State", width=24),
            DataColumn(header="Records", width=12),
        ),
        rows=orphan_rows,
        row_details=orphan_details,
        footer_renderables=(Notice.info(f"{len(candidates)} orphan candidate(s)."),),
    )


@plugins_app.command("drift")
def plugins_drift(
    ctx: typer.Context,
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    ack: Annotated[
        bool,
        typer.Option(
            "--ack",
            help="Set the current snapshot as the new baseline and exit.",
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit with code 1 if any drift is detected.",
        ),
    ] = False,
    baseline_name: Annotated[
        str,
        typer.Option(
            "--baseline",
            help=f"Named baseline to compare against (default: {DEFAULT_BASELINE_NAME}).",
        ),
    ] = DEFAULT_BASELINE_NAME,
) -> None:
    """Show plugin drift on an instance since the last baseline."""
    _validate_format(output_format)
    try:
        validate_baseline_name(baseline_name)
    except InvalidBaselineNameError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc
    meta, inventory = _load_inventory_or_exit(instance)
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)

    if ack:
        registry.save_plugin_baseline(meta.profile, baseline_name, inventory)
        captured = inventory.captured_at.strftime("%Y-%m-%d")
        console.print(
            Notice.info(f"Baseline set: {len(inventory.plugins)} plugins captured {captured}.")
        )
        return

    baseline = registry.load_plugin_baseline(meta.profile, baseline_name)
    if baseline is None:
        err_console.print(Notice.error(f"No baseline set for {meta.profile!r}."))
        console.print(
            Hint(
                label="Set baseline",
                command=f"nexus plugins drift --ack --baseline {baseline_name}",
            )
        )
        raise typer.Exit(1)

    report = compute_drift(baseline, inventory, meta.profile)

    if output_format == "json":
        _emit_json(report)
        if strict and report.entries:
            raise typer.Exit(1)
        return

    if not report.entries:
        console.print(Notice.info("No drift detected."))
        return

    drift_rows: RowsType = tuple(drift_row(e) for e in report.entries)
    drift_details: DetailsType = tuple(drift_detail_panel(e) for e in report.entries)
    _emit_framed_view(
        ctx,
        header_renderables=_plugins_header_renderables(),
        expandable_renderables=_plugins_expandable_renderables(),
        title=f"Plugin drift: {meta.profile}",
        columns=(
            DataColumn(header="Plugin ID", width=32),
            DataColumn(header="Name", width=20),
            DataColumn(header="Product", width=14),
            DataColumn(header="Status", width=16),
            DataColumn(header="Baseline ver", width=12),
            DataColumn(header="Current ver", width=12),
            DataColumn(header="Baseline state", width=14),
            DataColumn(header="Current state", width=14),
        ),
        rows=drift_rows,
        row_details=drift_details,
        footer_renderables=(
            Notice.info(status_breakdown((e.status for e in report.entries), "drift")),
        ),
    )
    if strict and report.entries:
        raise typer.Exit(1)


@plugins_app.command("explain")
def plugins_explain(
    plugin_id: Annotated[str, typer.Argument(help="Plugin to explain.")],
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Explain what a plugin does and whether the user likely needs it."""
    _, inventory = _load_inventory_or_exit(instance)
    plugin = next((p for p in inventory.plugins if p.plugin_id == plugin_id), None)
    if plugin is None:
        console.print(Notice.error(f"Plugin not found: {plugin_id}"))
        raise typer.Exit(1)
    _registry, meta, token, _expiry = _acquire_token(instance)
    transport = _impact_transport()
    impact = asyncio.run(
        compute_impact(
            inventory,
            plugin_id,
            url=meta.url,
            token=token,
            transport=transport,
            cross_scope=False,
        )
    )
    db = AdvisoryDatabase.load()
    single_plugin_inventory = inventory.model_copy(update={"plugins": (plugin,)})
    plugin_findings = compute_advisories(single_plugin_inventory, db, today=_today()).findings
    prompt = build_explain_context(plugin, impact, plugin_findings)
    client = _agent_client_factory()
    try:
        text = asyncio.run(client.complete(prompt, system=EXPLAIN_SYSTEM_PROMPT, model=AI_MODEL))
    except AnthropicError as exc:
        console.print(Notice.error(f"AI request failed: {exc}"))
        raise typer.Exit(1) from exc
    console.print(text)


@plugins_app.command("roadmap")
def plugins_roadmap(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Draft an AI-generated remediation roadmap."""
    meta, inventory = _load_inventory_or_exit(instance)
    db = AdvisoryDatabase.load()
    advisories = compute_advisories(inventory, db, today=_today())
    orphans = orphan_candidates(inventory)

    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    overrides = registry.load_advisory_overrides(meta.profile)
    deferred = len(overrides.overrides)

    if not advisories.findings and not orphans and deferred == 0:
        console.print(Notice.info("Nothing to remediate -- no advisories, orphans, or overrides."))
        return

    prompt = build_roadmap_context(inventory, advisories, orphans=orphans, deferred_count=deferred)
    client = _agent_client_factory()
    try:
        text = asyncio.run(client.complete(prompt, system=ROADMAP_SYSTEM_PROMPT, model=AI_MODEL))
    except AnthropicError as exc:
        console.print(Notice.error(f"AI request failed: {exc}"))
        raise typer.Exit(1) from exc
    console.print(text)


@recommend_app.callback(invoke_without_command=True)
def plugins_recommend_callback(ctx: typer.Context) -> None:
    """Show the available 'plugins recommend' subcommands."""
    if ctx.invoked_subcommand is not None:
        return
    console.print(CommandHelp(title="nexus plugins recommend", entry=PLUGINS_RECOMMEND_PARENT))
    console.print(
        CommandGuide(
            app_name="nexus plugins recommend",
            items=guide_items(PLUGINS_RECOMMEND_HELP),
        )
    )


@recommend_app.command("deactivate")
def plugins_recommend_deactivate(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """List plugins safest to deactivate, with AI rationale."""
    _, inventory = _load_inventory_or_exit(instance)
    db = AdvisoryDatabase.load()
    advisories = compute_advisories(inventory, db, today=_today())
    orphans = orphan_candidates(inventory)
    if not orphans and not advisories.findings:
        console.print(Notice.info("No orphans or advisories -- nothing to recommend."))
        return
    prompt = build_deactivation_context(inventory, advisories, orphans=orphans)
    client = _agent_client_factory()
    try:
        text = asyncio.run(client.complete(prompt, system=DEACTIVATE_SYSTEM_PROMPT, model=AI_MODEL))
    except AnthropicError as exc:
        console.print(Notice.error(f"AI request failed: {exc}"))
        raise typer.Exit(1) from exc
    console.print(text)


@baselines_app.callback(invoke_without_command=True)
def plugins_baselines_callback(ctx: typer.Context) -> None:
    """Show the available 'plugins baselines' subcommands."""
    if ctx.invoked_subcommand is not None:
        return
    console.print(CommandHelp(title="nexus plugins baselines", entry=PLUGINS_BASELINES_PARENT))
    console.print(
        CommandGuide(
            app_name="nexus plugins baselines",
            items=guide_items(PLUGINS_BASELINES_HELP),
        )
    )


@baselines_app.command("list")
def plugins_baselines_list(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
) -> None:
    """Show all named baselines for an instance."""
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    summaries = registry.list_plugin_baseline_summaries(meta.profile)
    if not summaries:
        console.print(Notice.info(f"No baselines saved for {meta.profile}."))
        return
    rows: list[list[RenderableType]] = [
        [name, captured[:19], str(count)] for name, captured, count in summaries
    ]
    console.print(
        DataTable(
            title=f"Baselines for instance {meta.profile}",
            columns=[
                DataColumn(header="Name", width=24),
                DataColumn(header="Captured", width=20),
                DataColumn(header="Plugins", width=8),
            ],
            rows=rows,
        )
    )


@baselines_app.command("delete")
def plugins_baselines_delete(
    name: Annotated[str, typer.Argument(help="Baseline name to delete.")],
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip confirmation."),
    ] = False,
) -> None:
    """Delete a named baseline."""
    try:
        validate_baseline_name(name)
    except InvalidBaselineNameError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc
    paths = NexusPaths.from_env()
    registry = InstanceRegistry(paths.instances_dir)
    meta, _ = _load_inventory_or_exit(instance)
    if not yes:
        confirmed = typer.confirm(f"Delete baseline {name!r} for {meta.profile}?")
        if not confirmed:
            console.print(Notice.info("Aborted."))
            return
    try:
        registry.delete_plugin_baseline(meta.profile, name)
    except BaselineNotFoundError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc
    console.print(Notice.info(f"Deleted baseline {name}"))
