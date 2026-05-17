# src/nexus/cli/commands_plugins_outdated.py
# Read-only `nexus plugins outdated` command (brew/apt-style).
# Author: Pierre Grothe
# Date: 2026-05-16
"""`nexus plugins outdated` -- list pending plugin updates.

Read-only listing, modelled on `brew outdated` / `apt list --upgradable`.
The destructive batch path lives on `nexus plugins upgrade` (no flag,
or with ``--family``); this module never mutates instance state.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
import yaml as _yaml

from nexus.cli.apps import plugins_app
from nexus.cli.console import console
from nexus.cli.formats import _emit_json, _UpdatesReport, _validate_format
from nexus.cli.renderables import plugin_detail_panel
from nexus.cli.views import (
    _emit_framed_view,
    _load_inventory_or_exit,
    _plugins_expandable_renderables,
    _plugins_header_renderables,
    _validate_family_filter,
)
from nexus.plugins.updates import plugins_with_updates
from nexus.ui import DataColumn, Hint, Notice

if TYPE_CHECKING:

    from nexus.ui.components.framed_viewer import DetailsType, RowsType


__all__: list[str] = []


@plugins_app.command("outdated")
def plugins_outdated(
    ctx: typer.Context,
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    family: Annotated[
        list[str] | None,
        typer.Option(
            "--family",
            help="Filter to one or more product families (case-insensitive). Repeatable.",
        ),
    ] = None,
    queue: Annotated[
        str,
        typer.Option(
            "--queue",
            help="Write a YAML queue of pending updates to the given path "
            "(writes an empty updates list when up-to-date).",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    """List plugins with newer versions available (brew/apt-style)."""
    _validate_format(output_format)
    meta, inventory = _load_inventory_or_exit(instance)
    pending = plugins_with_updates(inventory)
    if family:
        from nexus.plugins.filters import filter_by_family  # noqa: PLC0415

        _validate_family_filter(inventory, tuple(family))
        pending = filter_by_family(pending, tuple(family))
    if queue:
        payload: dict[str, object] = {
            "instance": meta.profile,
            "captured_at": inventory.captured_at.isoformat(),
            "updates": [
                {
                    "plugin_id": p.plugin_id,
                    "name": p.name,
                    "product_family": p.product_family,
                    "current_version": p.version,
                    "latest_version": p.latest_version,
                }
                for p in pending
            ],
        }
        Path(queue).write_text(_yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    if output_format == "json":
        _emit_json(_UpdatesReport(updates=tuple(pending)))
        return
    if not pending:
        with_lv = sum(1 for p in inventory.plugins if p.latest_version is not None)
        if with_lv == 0:
            console.print(
                Notice.warn(
                    "No latest_version data captured -- updates cannot be detected. "
                    "Likely causes: sys_store_app REST access denied (403), or "
                    "v_plugin's available_version mirrors version on this instance."
                )
            )
            console.print(
                Hint(
                    label="Grant role",
                    command="grant the OAuth user 'app_store_pa_user_role' on the SN instance",
                )
            )
        else:
            console.print(Notice.info("Up to date."))
        if queue:
            console.print(Notice.info(f"Wrote empty queue to {queue}."))
        return
    update_rows: RowsType = tuple(
        (p.plugin_id, p.name, p.product_family, p.version, p.latest_version or "-") for p in pending
    )
    update_details: DetailsType = tuple(plugin_detail_panel(p) for p in pending)
    _emit_framed_view(
        ctx,
        header_renderables=_plugins_header_renderables(),
        expandable_renderables=_plugins_expandable_renderables(),
        title=f"Outdated plugins -- {meta.profile}",
        columns=(
            DataColumn(header="Plugin ID", width=32),
            DataColumn(header="Name", width=20),
            DataColumn(header="Product", width=14),
            DataColumn(header="Current", width=12),
            DataColumn(header="Latest", width=12),
        ),
        rows=update_rows,
        row_details=update_details,
        footer_renderables=(Notice.info(f"{len(pending)} update(s) available."),),
    )
    if queue:
        console.print(Notice.info(f"Wrote queue ({len(pending)} entries) to {queue}."))
        console.print(
            Hint(
                label="Before applying",
                command=f"nexus instance refresh {meta.profile}",
            )
        )
