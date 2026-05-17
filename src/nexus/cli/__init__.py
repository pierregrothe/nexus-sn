# src/nexus/cli/__init__.py
# Typer CLI entry point for NEXUS.
# Author: Pierre Grothe
# Date: 2026-05-07
"""NEXUS command-line interface.

This module is now a thin entry point: it registers the root ``@app.callback``
and imports each ``commands_*`` sibling module for its decorator side-effects.
The actual command implementations live in those sibling modules per ADR-023.
"""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from nexus.cli import commands_capture as commands_capture
from nexus.cli import commands_instance as commands_instance
from nexus.cli import commands_plugins_advisories as commands_plugins_advisories
from nexus.cli import commands_plugins_analysis as commands_plugins_analysis
from nexus.cli import commands_plugins_basic as commands_plugins_basic
from nexus.cli import commands_plugins_exec as commands_plugins_exec
from nexus.cli import commands_plugins_outdated as commands_plugins_outdated
from nexus.cli import commands_top as commands_top
from nexus.cli.apps import app
from nexus.cli.auth import acquire_token as _acquire_token
from nexus.cli.console import console
from nexus.cli.console import render_context as _render_context
from nexus.cli.help_text import NEXUS_PARENT, TOP_LEVEL_HELP, guide_items
from nexus.connectors.servicenow.client import ServiceNowClient as ServiceNowClient
from nexus.plugins.advisories import AdvisoryDatabase as AdvisoryDatabase
from nexus.ui import CommandGuide, CommandHelp
from nexus.updater import check_and_maybe_update

__all__ = [
    "AdvisoryDatabase",
    "ServiceNowClient",
    "_acquire_token",
    "app",
    "commands_capture",
    "commands_instance",
    "commands_plugins_advisories",
    "commands_plugins_analysis",
    "commands_plugins_basic",
    "commands_plugins_exec",
    "commands_plugins_outdated",
    "commands_top",
]

log = logging.getLogger(__name__)


def _configure_logging(level: str = "WARNING") -> None:
    """Set up the root logger with a basic format.

    Args:
        level: Name of a stdlib logging level (case-insensitive).
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    log_level: Annotated[str, typer.Option("--log-level", envvar="NEXUS_LOG_LEVEL")] = "WARNING",
    plain: Annotated[
        bool,
        typer.Option(
            "--plain",
            help="Force machine-readable output: no colour, no pager, "
            "tab-separated tables, line-per-event progress.",
        ),
    ] = False,
) -> None:
    """NEXUS -- ServiceNow AI architect agent."""
    del plain  # Already honored at Console construction via argv pre-scan; flag declared for help text.
    _configure_logging(log_level)
    ctx.obj = _render_context
    check_and_maybe_update()
    if ctx.invoked_subcommand is None:
        console.print(CommandHelp(title="nexus", entry=NEXUS_PARENT))
        console.print(CommandGuide(app_name="nexus", items=guide_items(TOP_LEVEL_HELP)))


if __name__ == "__main__":
    app()
