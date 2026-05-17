# src/nexus/cli/commands_plugins_basic.py
# Typer commands for read-only plugin inventory ops (list, info, export, diff, promote).
# Author: Pierre Grothe
# Date: 2026-05-16
"""`nexus plugins` read-only commands.

Extracted from ``cli/__init__.py`` per ADR-023. Contains the
``list/info/export/diff/promote`` commands plus the plugins-app callback
that prints the help block when no subcommand is given. Everything here
is read-only against locally cached inventory; nothing here hits the
ServiceNow API.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
import yaml as _yaml

from nexus.cli.apps import plugins_app
from nexus.cli.console import console, err_console
from nexus.cli.renderables import (
    diff_detail_panel,
    diff_row,
    plugin_detail_panel,
    status_breakdown,
)
from nexus.cli.views import (
    _emit_framed_view,
    _emit_plugins_header,
    _load_inventory_or_exit,
    _plugins_expandable_renderables,
    _plugins_for,
    _plugins_header_renderables,
)
from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
from nexus.plugins.models import PluginInfo
from nexus.ui import (
    DataColumn,
    Hint,
    KeyValuePanel,
    KvRow,
    Notice,
    StatusBadge,
)

if TYPE_CHECKING:
    from rich.console import RenderableType

    from nexus.ui.components.framed_viewer import DetailsType, RowsType

from nexus.cli.formats import _emit_json, _validate_format

__all__: list[str] = []


@plugins_app.callback(invoke_without_command=True)
def plugins_callback(ctx: typer.Context) -> None:
    """Show the plugin inventory and the available subcommands."""
    if ctx.invoked_subcommand is not None:
        return
    _emit_plugins_header()


@plugins_app.command("list")
def plugins_list(
    ctx: typer.Context,
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
    product: Annotated[
        str, typer.Option("--product", help="Filter by product family (e.g. ITSM)")
    ] = "",
    source: Annotated[
        str, typer.Option("--source", help="Filter by source (servicenow|store|custom)")
    ] = "",
    state: Annotated[str, typer.Option("--state", help="Filter by state (active|inactive)")] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """Show all plugins installed on the resolved instance."""
    _validate_format(output_format)
    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        return
    meta, inv = resolved
    plugins = inv.plugins
    if product:
        plugins = tuple(p for p in plugins if p.product_family == product)
    if source:
        plugins = tuple(p for p in plugins if p.source == source)
    if state:
        plugins = tuple(p for p in plugins if p.state == state)
    if output_format == "json":
        _emit_json(inv.model_copy(update={"plugins": tuple(plugins)}))
        return
    if not plugins:
        console.print(Notice.info("No plugins match the requested filters."))
        return
    sorted_plugins = sorted(plugins, key=lambda x: (x.product_family, x.plugin_id))

    def _build_rows(plugin_list: tuple[PluginInfo, ...]) -> tuple[RowsType, DetailsType]:
        """Build (rows, details) from a list of PluginInfo for the TUI."""
        rows_out: list[tuple[RenderableType, ...]] = []
        details_out: list[RenderableType] = []
        for plug in plugin_list:
            state_badge = (
                StatusBadge.ok(plug.state)
                if plug.state == "active"
                else StatusBadge.warn(plug.state)
            )
            rows_out.append(
                (
                    plug.plugin_id,
                    plug.name,
                    plug.version,
                    state_badge,
                    plug.source,
                    plug.product_family,
                )
            )
            details_out.append(plugin_detail_panel(plug))
        return tuple(rows_out), tuple(details_out)

    initial_rows, initial_details = _build_rows(tuple(sorted_plugins))

    def _refresh() -> tuple[RowsType, DetailsType]:
        """Re-read the cached inventory and rebuild rows + details."""
        latest = _plugins_for(instance)
        if latest is None:
            return ((), ())
        _, latest_inv = latest
        pool = latest_inv.plugins
        if product:
            pool = tuple(p for p in pool if p.product_family == product)
        if source:
            pool = tuple(p for p in pool if p.source == source)
        if state:
            pool = tuple(p for p in pool if p.state == state)
        ordered = tuple(sorted(pool, key=lambda x: (x.product_family, x.plugin_id)))
        return _build_rows(ordered)

    _emit_framed_view(
        ctx,
        header_renderables=_plugins_header_renderables(),
        expandable_renderables=_plugins_expandable_renderables(),
        title=f"Plugins -- {meta.profile}",
        columns=(
            DataColumn(header="Plugin ID", width=32),
            DataColumn(header="Name", width=24),
            DataColumn(header="Version", width=10),
            DataColumn(header="State", width=10),
            DataColumn(header="Source", width=11),
            DataColumn(header="Product", width=14),
        ),
        rows=initial_rows,
        row_details=initial_details,
        refresh_callback=_refresh,
        footer_renderables=(Notice.info(f"{len(initial_rows)} plugin(s) shown."),),
    )


@plugins_app.command("info")
def plugins_info(
    plugin_id: Annotated[str, typer.Argument(help="SN plugin identifier (e.g. com.snc.incident)")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """Show full details and direct dependencies for one plugin."""
    _validate_format(output_format)
    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    _, inv = resolved
    plugins = inv.plugins
    plugin = next((p for p in plugins if p.plugin_id == plugin_id), None)
    if plugin is None:
        err_console.print(Notice.error(f"Plugin {plugin_id!r} not found in inventory."))
        raise typer.Exit(1)
    if output_format == "json":
        _emit_json(plugin)
        return
    console.print(
        KeyValuePanel(
            title=plugin.name,
            rows=[
                KvRow(label="Plugin ID", value=plugin.plugin_id),
                KvRow(label="Version", value=plugin.version),
                KvRow(
                    label="State",
                    value=(
                        StatusBadge.ok(plugin.state)
                        if plugin.state == "active"
                        else StatusBadge.warn(plugin.state)
                    ),
                ),
                KvRow(label="Source", value=plugin.source),
                KvRow(label="Product family", value=plugin.product_family),
                KvRow(label="sys_id", value=plugin.sys_id),
                KvRow(
                    label="Installed at",
                    value=(
                        plugin.installed_at.strftime("%Y-%m-%d %H:%M UTC")
                        if plugin.installed_at
                        else "-"
                    ),
                ),
            ],
        )
    )
    if plugin.depends_on:
        console.print(
            Hint(
                label="Depends on",
                command=", ".join(plugin.depends_on),
            )
        )


_PLUGIN_CSV_FIELDS = (
    "plugin_id",
    "name",
    "version",
    "state",
    "source",
    "product_family",
    "sys_id",
    "installed_at",
)


@plugins_app.command("export")
def plugins_export(
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    fmt: Annotated[str, typer.Option("--format", help="Output format (yaml|csv)")] = "yaml",
    out: Annotated[
        str, typer.Option("--out", help="Output file path (default: plugins.<ext>)")
    ] = "",
) -> None:
    """Write the plugin inventory to a YAML or CSV file."""
    if fmt not in ("yaml", "csv"):
        err_console.print(Notice.error(f"Unknown format {fmt!r}; use yaml or csv."))
        raise typer.Exit(1)
    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    _, inv = resolved
    plugins = inv.plugins
    path = Path(out) if out else Path(f"plugins.{fmt}")
    if fmt == "yaml":
        payload = {
            "plugins": [
                {
                    field: (
                        (p.installed_at.isoformat() if p.installed_at else None)
                        if field == "installed_at"
                        else getattr(p, field)
                    )
                    for field in _PLUGIN_CSV_FIELDS
                }
                for p in plugins
            ]
        }
        path.write_text(_yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    else:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(_PLUGIN_CSV_FIELDS)
            for p in plugins:
                writer.writerow(
                    [
                        p.plugin_id,
                        p.name,
                        p.version,
                        p.state,
                        p.source,
                        p.product_family,
                        p.sys_id,
                        p.installed_at.isoformat() if p.installed_at else "",
                    ]
                )
    console.print(Notice.info(f"Wrote {len(plugins)} plugins to {path}"))


@plugins_app.command("diff")
def plugins_diff(
    ctx: typer.Context,
    profile_a: Annotated[str, typer.Argument(help="First profile")],
    profile_b: Annotated[str, typer.Argument(help="Second profile")],
    status: Annotated[
        str,
        typer.Option(
            "--status",
            help="Filter by status (only_in_a|only_in_b|version_mismatch|state_mismatch)",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """Show cross-instance plugin differences."""
    _validate_format(output_format)
    meta_a, inv_a = _load_inventory_or_exit(profile_a)
    meta_b, inv_b = _load_inventory_or_exit(profile_b)
    diff: PluginDiff = compute_diff(inv_a, inv_b, meta_a.profile, meta_b.profile)
    entries: tuple[PluginDiffEntry, ...] = diff.entries
    if status:
        entries = tuple(e for e in entries if e.status == status)

    if output_format == "json":
        _emit_json(diff.model_copy(update={"entries": entries}))
        return

    if not entries:
        console.print(Notice.info("No differences found."))
        return
    diff_rows: RowsType = tuple(diff_row(e) for e in entries)
    diff_details: DetailsType = tuple(
        diff_detail_panel(e, meta_a.profile, meta_b.profile) for e in entries
    )

    def _refresh() -> tuple[RowsType, DetailsType]:
        """Re-read both inventories and recompute the diff."""
        meta_a_new, inv_a_new = _load_inventory_or_exit(profile_a)
        meta_b_new, inv_b_new = _load_inventory_or_exit(profile_b)
        diff_new = compute_diff(inv_a_new, inv_b_new, meta_a_new.profile, meta_b_new.profile)
        entries_new = diff_new.entries
        if status:
            entries_new = tuple(e for e in entries_new if e.status == status)
        rows_new: RowsType = tuple(diff_row(e) for e in entries_new)
        details_new: DetailsType = tuple(
            diff_detail_panel(e, meta_a_new.profile, meta_b_new.profile) for e in entries_new
        )
        return rows_new, details_new

    _emit_framed_view(
        ctx,
        header_renderables=_plugins_header_renderables(),
        expandable_renderables=_plugins_expandable_renderables(),
        title=f"Plugins: {meta_a.profile} vs {meta_b.profile}",
        columns=(
            DataColumn(header="Plugin ID", width=32),
            DataColumn(header="Name", width=20),
            DataColumn(header="Product", width=14),
            DataColumn(header="Status", width=18),
            DataColumn(header="A version", width=10),
            DataColumn(header="B version", width=10),
            DataColumn(header="A state", width=9),
            DataColumn(header="B state", width=9),
        ),
        rows=diff_rows,
        row_details=diff_details,
        refresh_callback=_refresh,
        footer_renderables=(
            Notice.info(status_breakdown((e.status for e in entries), "difference")),
        ),
    )


def _promote_payload(plan: PromotionPlan) -> dict[str, object]:
    """Serialise a PromotionPlan into the YAML payload shape."""
    bucket: dict[str, list[dict[str, object]]] = {
        "install": [],
        "activate": [],
        "upgrade": [],
    }
    for action in plan.actions:
        row: dict[str, object] = {
            "plugin_id": action.plugin_id,
            "name": action.name,
            "product_family": action.product_family,
            "target_version": action.target_version,
        }
        if action.current_version is not None:
            row["current_version"] = action.current_version
        bucket[action.action].append(row)
    return {
        "source_profile": plan.source_profile,
        "target_profile": plan.target_profile,
        "actions": bucket,
    }


@plugins_app.command("promote")
def plugins_promote(
    source: Annotated[str, typer.Argument(help="Source profile")],
    target: Annotated[
        str, typer.Option("--to", help="Target profile to bring up to match source.")
    ] = "",
    out: Annotated[
        str,
        typer.Option(
            "--out",
            help="Output YAML file (default: promote-<src>-to-<dst>.yaml)",
        ),
    ] = "",
) -> None:
    """Write an additive action plan to make <target> match <source>."""
    if source == target:
        err_console.print(
            Notice.error("Source and target are the same profile; nothing to promote.")
        )
        raise typer.Exit(1)
    meta_src, inv_src = _load_inventory_or_exit(source)
    meta_dst, inv_dst = _load_inventory_or_exit(target)
    diff = compute_diff(inv_src, inv_dst, meta_src.profile, meta_dst.profile)
    plan = project_to_promote_plan(diff)
    if not plan.actions:
        console.print(
            Notice.info(
                f"Target {meta_dst.profile!r} already matches "
                f"{meta_src.profile!r}. No actions written."
            )
        )
        return
    path = Path(out) if out else Path(f"promote-{meta_src.profile}-to-{meta_dst.profile}.yaml")
    payload = _promote_payload(plan)
    path.write_text(_yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    counts: dict[str, int] = {"install": 0, "activate": 0, "upgrade": 0}
    for action in plan.actions:
        counts[action.action] += 1
    console.print(
        KeyValuePanel(
            title="Promotion plan",
            rows=[
                KvRow(
                    label="Source",
                    value=(
                        f"{meta_src.profile} "
                        f"(captured {inv_src.captured_at.strftime('%Y-%m-%d %H:%M UTC')})"
                    ),
                ),
                KvRow(
                    label="Target",
                    value=(
                        f"{meta_dst.profile} "
                        f"(captured {inv_dst.captured_at.strftime('%Y-%m-%d %H:%M UTC')})"
                    ),
                ),
                KvRow(label="Install", value=str(counts["install"])),
                KvRow(label="Activate", value=str(counts["activate"])),
                KvRow(label="Upgrade", value=str(counts["upgrade"])),
                KvRow(label="Output", value=str(path)),
            ],
        )
    )
