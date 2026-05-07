# nexus/cli.py
# Typer CLI entry point for NEXUS.
# Author: Pierre Grothe
# Date: 2026-05-07

"""NEXUS command-line interface.

All commands validate config and credentials at startup.
Features requiring unavailable MCP servers are hidden from help text.
"""

import logging
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths

log = logging.getLogger(__name__)

app = typer.Typer(
    name="nexus",
    help="NEXUS -- ServiceNow AI architect agent",
    no_args_is_help=True,
)

console = Console()
err_console = Console(stderr=True)


def _configure_logging(level: str = "WARNING") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


@app.callback()
def main(
    log_level: Annotated[str, typer.Option("--log-level", envvar="NEXUS_LOG_LEVEL")] = "WARNING",
) -> None:
    """NEXUS -- ServiceNow AI architect agent."""
    _configure_logging(log_level)


@app.command()
def setup() -> None:
    """First-run wizard: configure credentials, instances, and sync templates."""
    console.print("[bold]NEXUS Setup[/bold]")
    console.print("Interactive setup wizard -- not yet implemented.")
    console.print("Configure manually by editing ~/.nexus/config.yaml")


@app.command()
def status() -> None:
    """Show instance connection status and available capabilities."""
    paths = NexusPaths.from_env()
    manager = ConfigManager(paths)

    if not manager.exists():
        err_console.print("[yellow]No config found. Run 'nexus setup' first.[/yellow]")
        raise typer.Exit(code=1)

    config = manager.load()

    table = Table(title="NEXUS Status")
    table.add_column("Item", style="bold")
    table.add_column("Value")

    table.add_row("Config", str(paths.config_file))
    table.add_row("Default instance", config.instances.default or "(none)")
    table.add_row("GitHub repo", config.preferences.github_repo or "(not configured)")
    table.add_row("MCP auto-probe", str(config.capabilities.auto_probe))

    console.print(table)


@app.command()
def sync() -> None:
    """Pull the latest templates from the GitHub registry."""
    console.print("Syncing templates -- not yet implemented.")
    console.print("Configure github_repo in ~/.nexus/config.yaml first.")


@app.command("templates")
def templates_cmd() -> None:
    """Browse and inspect available templates."""
    console.print("Template browser -- not yet implemented. Run 'nexus sync' first.")


@app.command()
def assess(
    for_template: Annotated[
        str, typer.Option("--for", help="Check readiness for a specific template")
    ] = "",
    job: Annotated[str, typer.Option("--job", help="Validate a past deployment by job ID")] = "",
) -> None:
    """Run an instance health scan or targeted assessment."""
    if for_template:
        console.print(f"Readiness check for template: {for_template!r} -- not yet implemented.")
    elif job:
        console.print(f"Post-deploy validation for job: {job!r} -- not yet implemented.")
    else:
        console.print("Instance health scan -- not yet implemented.")


@app.command()
def apply(
    template: Annotated[str, typer.Argument(help="Template name to deploy")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Deploy a template to the configured ServiceNow instance."""
    console.print(f"Applying template: {template!r} (dry_run={dry_run}) -- not yet implemented.")


@app.command()
def run(
    request: Annotated[str, typer.Argument(help="Free-form orchestration request")],
) -> None:
    """Free-form AI orchestration request."""
    console.print(f"Running: {request!r} -- not yet implemented.")


@app.command()
def rollback(
    job_id: Annotated[str, typer.Argument(help="Job ID to roll back")],
) -> None:
    """Undo a previous deployment by job ID."""
    console.print(f"Rolling back job: {job_id!r} -- not yet implemented.")


@app.command()
def ui() -> None:
    """Start the NiceGUI dashboard (requires pip install nexus-sn[ui])."""
    try:
        from nexus.ui.app import start_ui  # type: ignore[import]
        start_ui()
    except ImportError:
        err_console.print(
            "[red]NiceGUI not installed.[/red] "
            "Run: pip install nexus-sn[ui]"
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
