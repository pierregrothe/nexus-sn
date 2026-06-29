# src/nexus/cli/commands_top.py
# Typer command bodies for top-level `nexus` commands (status, reauth, update, ...).
# Author: Pierre Grothe
# Date: 2026-05-16
"""Top-level Typer commands for the NEXUS CLI.

Extracted from ``cli/__init__.py`` per ADR-023 to keep the entry-point
file marching toward the 800-line cap. Each command is a thin handler
that delegates to domain modules; nothing here owns state.
"""

from __future__ import annotations

from typing import Annotated

import typer
from packaging.version import InvalidVersion, parse

from nexus.cache import clear_cache
from nexus.capabilities.feature_flags import claude_ai_name_for
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.status_reporter import StatusReporter
from nexus.capabilities.tier import TierDetector
from nexus.cli.apps import app
from nexus.cli.auth import detect_tier as _detect_tier
from nexus.cli.console import console, err_console
from nexus.cli.console import render_context as _render_context
from nexus.ui import KeyValuePanel, KvRow, Notice
from nexus.ui.app import start_ui
from nexus.ui.banner import print_banner
from nexus.updater import check_and_maybe_update, current_version
from nexus.updater.client import GitHubReleasesClient

__all__: list[str] = []


@app.command()
def status(
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Clear cached tier detection and re-detect")
    ] = False,
) -> None:
    """Show NEXUS tier and available enterprise MCP servers."""
    if refresh:
        clear_cache(TierDetector.detect)

    print_banner(console)
    detection = _detect_tier()
    capabilities = CapabilitySet.from_detection(detection)
    StatusReporter(console=console).print(detection, capabilities, render_context=_render_context)


@app.command()
def reauth(
    server: Annotated[
        str | None,
        typer.Option(
            "--server",
            help="Name of the MCP server to re-authenticate (lowercase enum value, e.g. 'marketing')",
        ),
    ] = None,
) -> None:
    """Print the command to re-authenticate one or more MCP servers."""
    detection = _detect_tier()

    if server is not None:
        target = next((srv for srv in detection.needs_reauth_servers if srv.value == server), None)
        if target is None:
            err_console.print(
                Notice.error(
                    f"Server {server!r} is not currently flagged for re-auth. "
                    f"Run `nexus status --refresh` if you think this is wrong."
                )
            )
            raise typer.Exit(code=1)
        console.print(f'claude /mcp "{claude_ai_name_for(target)}"')
        return

    if not detection.needs_reauth_servers:
        console.print(Notice.info("All MCP servers authenticated. Nothing to do."))
        return

    console.print(
        KeyValuePanel(
            title="Re-auth commands",
            rows=[
                KvRow(label=srv.value, value=f'claude /mcp "{claude_ai_name_for(srv)}"')
                for srv in sorted(detection.needs_reauth_servers, key=lambda s: s.value)
            ],
        )
    )


@app.command()
def update(
    check_only: Annotated[
        bool,
        typer.Option("--check-only", help="Only report; do not install"),
    ] = False,
) -> None:
    """Manually check for updates (and install unless --check-only).

    Plain ``nexus update`` runs the same auto-update path the CLI callback
    triggers. With ``--check-only``, fetch and report without installing.
    """
    if not check_only:
        check_and_maybe_update()
        return

    current = current_version()
    if current is None:
        console.print(Notice.info("nexus-sn is not installed as a distribution; cannot check."))
        return

    info = GitHubReleasesClient().fetch_latest()
    if info is None:
        console.print(Notice.info("Could not reach GitHub. No update info available."))
        return

    try:
        if parse(info.tag_name) <= parse(current):
            console.print(Notice.info(f"Up to date ({current})"))
            return
    except InvalidVersion:
        console.print(Notice.warn(f"Latest tag {info.tag_name!r} is not a valid version; skipping"))
        return

    console.print(Notice.info(f"Update available: {current} -> {info.tag_name}"))


@app.command()
def apply(
    template: Annotated[str, typer.Argument(help="Template name to deploy")],
    scope: Annotated[
        str, typer.Option("--scope", help="Override the template's declared target_scope")
    ] = "",
    force: Annotated[bool, typer.Option("--force", help="Skip Gate 1 BLOCK (not ERROR)")] = False,
    skip_gate2: Annotated[
        bool, typer.Option("--skip-gate2", help="Run apply without post-apply Gate 2")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Reserved -- not implemented in v1")
    ] = False,
) -> None:
    """Deploy a template to the configured ServiceNow instance."""
    if dry_run:
        console.print(Notice.error("--dry-run is not implemented in v1"))
        raise typer.Exit(1)

    from nexus.cli.commands_apply import (  # noqa: PLC0415
        default_apply_collaborators,
        run_apply,
    )
    from nexus.config.paths import NexusPaths  # noqa: PLC0415

    paths = NexusPaths.from_env()
    exit_code = run_apply(
        template_id=template,
        scope_override=scope,
        force=force,
        skip_gate2=skip_gate2,
        render_context=_render_context,
        paths=paths,
        collaborators=default_apply_collaborators(paths),
    )
    raise typer.Exit(exit_code)


@app.command()
def run(
    request: Annotated[str, typer.Argument(help="Free-form orchestration request")],
) -> None:
    """Free-form AI orchestration request."""
    console.print(Notice.info(f"Running: {request!r} -- not yet implemented."))


@app.command()
def rollback(
    job_id: Annotated[str, typer.Argument(help="Job ID to roll back")],
) -> None:
    """Undo a previous deployment by job ID."""
    console.print(Notice.info(f"Rolling back job: {job_id!r} -- not yet implemented."))


@app.command()
def ui() -> None:
    """Start the NiceGUI dashboard (requires pip install nexus-sn[ui])."""
    try:
        start_ui()
    except ImportError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(code=1) from exc
