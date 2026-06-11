# src/nexus/cli/views.py
# Shared view helpers used by the plugin and capture command modules.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Rendering, inventory, and engine-construction helpers shared by command modules.

Extracted from ``cli/__init__.py`` per ADR-023. Anything that produces a
``RenderableType``, resolves a profile, or builds a transport-layer
client lives here once and is imported by every command module that
needs it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

import typer

from nexus.api.kroki_client import KrokiClient
from nexus.capture.engine import CaptureEngine
from nexus.cli.auth import acquire_token as _acquire_token
from nexus.cli.auth import resolve_profile as _resolve_profile
from nexus.cli.console import console
from nexus.cli.help_text import (
    CAPTURE_HELP,
    CAPTURE_PARENT,
    PLUGINS_HELP,
    PLUGINS_PARENT,
    guide_items,
)
from nexus.config.paths import NexusPaths
from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.instances.models import InstanceMeta
from nexus.instances.registry import InstanceRegistry
from nexus.plugins import PluginInventory, PluginScanner
from nexus.schema import SchemaCartographer
from nexus.schema.archive import SchemaArchiveReader
from nexus.schema.erd import MermaidErdEmitter
from nexus.schema.models import SchemaArea
from nexus.ui import CommandGuide, CommandHelp, DataColumn, DataTable, Hint, Notice
from nexus.ui.capabilities import RenderProfile
from nexus.ui.components.framed_viewer import FramedViewer, RefreshCallback
from nexus.ui.render_context import get_render_context

if TYPE_CHECKING:
    from rich.console import Console, RenderableType

__all__ = [
    "_build_capture_engine",
    "_build_offline_schema_renderer",
    "_build_schema_cartographer",
    "_capture_expandable_renderables",
    "_capture_header_renderables",
    "_emit_framed_view",
    "_emit_inline_view",
    "_emit_plugins_header",
    "_load_inventory_or_exit",
    "_plugins_expandable_renderables",
    "_plugins_for",
    "_plugins_header_renderables",
    "_rescan_plugin_inventory",
    "_validate_family_filter",
]


def _build_capture_engine(profile: str) -> tuple[CaptureEngine, ServiceNowClient]:
    """Build a CaptureEngine for the given registered instance profile.

    Args:
        profile: Instance profile name from InstanceRegistry.

    Returns:
        Tuple of (CaptureEngine, ServiceNowClient) for the caller to use.

    Raises:
        typer.Exit: With code 1 if the profile is not registered or expired.
    """
    _, meta, token, _ = _acquire_token(profile)
    client = ServiceNowClient(instance_url=meta.url, token=token)
    engine = CaptureEngine(client=client, archive_root=NexusPaths.from_env().archives_dir)
    return engine, client


def _build_schema_cartographer(
    profile: str,
    kroki_url: str,
    kroki_timeout: float,
    areas: Mapping[str, SchemaArea] | None = None,
) -> tuple[SchemaCartographer, ServiceNowClient]:
    """Build a SchemaCartographer for the given registered instance profile.

    Args:
        profile: Instance profile name from InstanceRegistry.
        kroki_url: Kroki render endpoint for diagram image export.
        kroki_timeout: Per-request Kroki timeout in seconds.
        areas: Area registry to inject. Uses DEFAULT_AREAS when None.

    Returns:
        Tuple of (SchemaCartographer, ServiceNowClient) for the caller to use.

    Raises:
        typer.Exit: With code 1 if the profile is not registered or expired.
    """
    from nexus.schema.areas import DEFAULT_AREAS  # noqa: PLC0415

    _, meta, token, _ = _acquire_token(profile)
    client = ServiceNowClient(instance_url=meta.url, token=token)
    cartographer = SchemaCartographer(
        client=client,
        areas=areas if areas is not None else DEFAULT_AREAS,
        archive_root=NexusPaths.from_env().schema_dir,
        kroki=KrokiClient(kroki_url, timeout=kroki_timeout),
    )
    return cartographer, client


def _build_offline_schema_renderer(
    kroki_url: str, kroki_timeout: float
) -> tuple[SchemaArchiveReader, MermaidErdEmitter, KrokiClient]:
    """Build the pieces needed to re-render an ERD from a saved snapshot.

    Offline counterpart to :func:`_build_schema_cartographer`: no auth, no
    instance access. The reader loads a SchemaGraph from JSON, the emitter
    renders it, and the Kroki client covers optional image export.

    Args:
        kroki_url: Kroki render endpoint for diagram image export.
        kroki_timeout: Per-request Kroki timeout in seconds.

    Returns:
        Tuple of (SchemaArchiveReader, MermaidErdEmitter, KrokiClient).
    """
    return (
        SchemaArchiveReader(),
        MermaidErdEmitter(),
        KrokiClient(kroki_url, timeout=kroki_timeout),
    )


def _plugins_for(profile: str) -> tuple[InstanceMeta, PluginInventory] | None:
    """Resolve a profile and return its plugin inventory, or None when missing.

    Args:
        profile: Instance profile name, or empty string to use the config default.

    Returns:
        Tuple of (meta, inventory) when an inventory exists, or ``None`` when the
        instance has no captured ``plugins.json``.
    """
    registry, meta = _resolve_profile(profile)
    inv = registry.load_plugin_inventory(meta.profile)
    if inv is None:
        return None
    return meta, inv


def _plugins_header_renderables() -> tuple[RenderableType, ...]:
    """Build the always-visible `nexus plugins` help block (purpose + example)."""
    return (CommandHelp(title="nexus plugins", entry=PLUGINS_PARENT),)


def _plugins_expandable_renderables() -> tuple[RenderableType, ...]:
    """Build the collapsed-by-default `nexus plugins` subcommand guide."""
    return (
        CommandGuide(
            app_name="nexus plugins",
            items=guide_items(PLUGINS_HELP),
            title="available commands",
        ),
    )


def _capture_header_renderables() -> tuple[RenderableType, ...]:
    """Build the always-visible `nexus capture` help block."""
    return (CommandHelp(title="nexus capture", entry=CAPTURE_PARENT),)


def _capture_expandable_renderables() -> tuple[RenderableType, ...]:
    """Build the collapsed-by-default `nexus capture` subcommand guide."""
    return (
        CommandGuide(
            app_name="nexus capture",
            items=guide_items(CAPTURE_HELP),
            title="available commands",
        ),
    )


def _emit_plugins_header() -> None:
    """Print the `nexus plugins` help + subcommand guide directly to stdout."""
    console.print(CommandHelp(title="nexus plugins", entry=PLUGINS_PARENT))
    console.print(
        CommandGuide(
            app_name="nexus plugins",
            items=guide_items(PLUGINS_HELP),
            title="available commands",
        )
    )


def _emit_inline_view(
    console: Console,
    *,
    header_renderables: tuple[RenderableType, ...],
    title: str,
    columns: tuple[DataColumn, ...],
    rows: tuple[tuple[RenderableType, ...], ...],
    footer_renderables: tuple[RenderableType, ...],
) -> None:
    """Print the view inline (no TUI) for LEGACY / PLAIN profiles or fallback."""
    for renderable in header_renderables:
        console.print(renderable)
    console.print(DataTable(title=title, columns=list(columns), rows=[list(r) for r in rows]))
    for renderable in footer_renderables:
        console.print(renderable)


def _emit_framed_view(
    ctx: typer.Context,
    *,
    header_renderables: tuple[RenderableType, ...],
    expandable_renderables: tuple[RenderableType, ...] = (),
    title: str,
    columns: tuple[DataColumn, ...],
    rows: tuple[tuple[RenderableType, ...], ...],
    row_details: tuple[RenderableType, ...] = (),
    refresh_callback: object | None = None,
    footer_renderables: tuple[RenderableType, ...],
) -> None:
    """Show a sticky-frame TUI on RICH/BASIC; fall back inline on LEGACY/PLAIN.

    The viewer pins the header + footer in place while the row body scrolls
    inside the frame. Column headers stay visible at the top of the table
    region. j/k/arrows/PgUp/PgDn/g/G navigate; q exits; ? toggles the
    expandable region (subcommand guide).

    Falls back to inline rendering (with a one-line warning) if the TUI
    cannot start -- for example, when stdin is not a real TTY or the
    terminal driver rejects full-screen mode.

    Args:
        ctx: Typer context (used to retrieve the active :class:`RenderContext`).
        header_renderables: Always-visible renderables above the table.
        expandable_renderables: Renderables shown only when the user presses
            ``?``. Typically a CommandGuide of subcommands. Empty tuple to
            hide the toggle entirely.
        title: Table title shown on the gradient top border.
        columns: Column descriptors used by the framed viewer.
        rows: Tuple of cell tuples; the scrollable body.
        row_details: Optional detail renderables parallel to ``rows``. When
            non-empty, Enter on a row opens the matching detail in a
            centered modal popup.
        refresh_callback: Optional zero-arg callable that returns a fresh
            ``(rows, details)`` pair. When provided, ``r`` reloads the view.
        footer_renderables: Renderables pinned below the table.
    """
    rctx = get_render_context(ctx)
    use_framed = rctx.profile in {RenderProfile.RICH, RenderProfile.BASIC} and rows
    if not use_framed:
        _emit_inline_view(
            rctx.console,
            header_renderables=header_renderables + expandable_renderables,
            title=title,
            columns=columns,
            rows=rows,
            footer_renderables=footer_renderables,
        )
        return
    typed_refresh = cast("RefreshCallback | None", refresh_callback)
    viewer = FramedViewer(
        header_renderables=header_renderables,
        expandable_renderables=expandable_renderables,
        title=title,
        columns=columns,
        rows=rows,
        row_details=row_details,
        footer_renderables=footer_renderables,
        refresh_callback=typed_refresh,
    )
    try:
        viewer.run(rctx.console)
    except Exception as exc:
        rctx.console.print(
            Notice.warn(
                f"Framed viewer unavailable ({exc.__class__.__name__}: {exc}); using inline render."
            )
        )
        _emit_inline_view(
            rctx.console,
            header_renderables=header_renderables + expandable_renderables,
            title=title,
            columns=columns,
            rows=rows,
            footer_renderables=footer_renderables,
        )


async def _rescan_plugin_inventory(
    meta: InstanceMeta,
    token: str,
    registry: InstanceRegistry,
    *,
    quiet: bool = False,
) -> PluginInventory | None:
    """Refresh the cached plugin inventory; persist + return the fresh result.

    Called from upgrade / batch-upgrade / apply-plan / outdated code paths
    when the cached inventory is stale or after a destructive operation.

    Best-effort: any scan error degrades to a warning + manual-refresh hint
    and returns ``None`` so callers can fall back to whatever they already
    had. ``capture_counts=False`` skips the per-plugin record fan-out for
    speed; users who need fresh orphan-detection counts can run a full
    ``nexus instance refresh``.

    Args:
        meta: Resolved instance metadata.
        token: Active bearer token for the instance.
        registry: Registry used to persist the fresh inventory.
        quiet: When True, suppress the leading "Refreshing plugin inventory..."
            notice so callers that already announced the refresh (with
            their own reason text) do not produce duplicate output.

    Returns:
        The freshly scanned ``PluginInventory`` on success, or ``None`` when
        the scan raises (the disk cache is untouched in that case).
    """
    if not quiet:
        console.print(Notice.info("Refreshing plugin inventory..."))
    scanner = PluginScanner()
    try:
        inventory = await scanner.scan(meta.url, token, meta.sn_version, capture_counts=False)
    except Exception as exc:
        console.print(Notice.warn(f"Plugin inventory rescan failed: {exc}"))
        console.print(
            Hint(
                label="Refresh manually",
                command=f"nexus instance refresh {meta.profile}",
            )
        )
        return None
    registry.save_plugin_inventory(meta.profile, inventory)
    console.print(Notice.info(f"Plugin inventory refreshed -- {len(inventory.plugins)} plugins."))
    return inventory


def _load_inventory_or_exit(profile: str) -> tuple[InstanceMeta, PluginInventory]:
    """Resolve a profile and load its plugin inventory, exiting with a Hint when empty.

    Args:
        profile: Profile name to resolve.

    Returns:
        Tuple of (meta, inventory) once the inventory is loaded.

    Raises:
        typer.Exit: When the profile has no captured plugin inventory.
    """
    registry, meta = _resolve_profile(profile)
    inv = registry.load_plugin_inventory(meta.profile)
    if inv is None:
        console.print(Notice.warn(f"Plugin inventory empty for {meta.profile!r}."))
        console.print(Hint(label="Refresh", command=f"nexus instance refresh {meta.profile}"))
        raise typer.Exit(1)
    return meta, inv


def _validate_family_filter(
    inventory: PluginInventory, families: tuple[str, ...]
) -> tuple[str, ...]:
    """Validate ``--family`` arguments against the curated taxonomy.

    On unknown family, prints the SAME-instance available-families table
    and raises ``typer.Exit(2)``. Returns the input tuple unchanged on
    success so callers can chain into ``filter_by_family``.

    Args:
        inventory: Current plugin inventory (used for the available-families
            error table).
        families: User-supplied family names from ``--family`` (repeatable).

    Returns:
        The same ``families`` tuple, unchanged.

    Raises:
        typer.Exit: With code 2 when one or more names do not match.
    """
    from nexus.plugins.filters import available_families, unknown_families  # noqa: PLC0415

    unknown = unknown_families(families)
    if not unknown:
        return families
    console.print(
        Notice.error(
            f"Unknown product family: {', '.join(unknown)}. "
            f"Available families on this instance:"
        )
    )
    rows: list[list[RenderableType]] = [
        [name, str(count)] for name, count in available_families(inventory.plugins)
    ]
    console.print(
        DataTable(
            title="Available families",
            columns=[
                DataColumn(header="Family", width=20),
                DataColumn(header="Plugins", width=10),
            ],
            rows=rows,
        )
    )
    raise typer.Exit(2)
