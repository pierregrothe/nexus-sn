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

from nexus.auth.keychain import KeychainClient
from nexus.cache import clear_cache
from nexus.capabilities.claude_config import FilesystemClaudeCodeConfigReader
from nexus.capabilities.feature_flags import MCPServer, claude_ai_name_for
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.status_reporter import StatusReporter
from nexus.capabilities.tier import TierDetector
from nexus.ui.app import start_ui

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
def status(
    refresh: Annotated[
        bool, typer.Option("--refresh", help="Clear cached tier detection and re-detect")
    ] = False,
) -> None:
    """Show NEXUS tier and available enterprise MCP servers."""
    if refresh:
        clear_cache(TierDetector.detect)

    reader = FilesystemClaudeCodeConfigReader(keychain=KeychainClient())
    detection = TierDetector(reader=reader).detect()
    capabilities = CapabilitySet.from_detection(detection)
    StatusReporter(console=console).print(detection, capabilities)


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
    reader = FilesystemClaudeCodeConfigReader(keychain=KeychainClient())
    detection = TierDetector(reader=reader).detect()

    if server is not None:
        target = _resolve_reauth_target(server, detection.needs_reauth_servers)
        if target is None:
            err_console.print(
                f"[red]Server {server!r} is not currently flagged for re-auth.[/red] "
                "Run `nexus status --refresh` if you think this is wrong."
            )
            raise typer.Exit(code=1)
        cmd = f'claude /mcp "{claude_ai_name_for(target)}"'
        console.print(cmd)
        return

    if not detection.needs_reauth_servers:
        console.print("All MCP servers authenticated. Nothing to do.")
        return

    sorted_servers = sorted(detection.needs_reauth_servers, key=lambda s: s.value)
    for srv in sorted_servers:
        cmd = f'claude /mcp "{claude_ai_name_for(srv)}"'
        console.print(f"  {srv.value}: {cmd}")


def _resolve_reauth_target(name: str, candidates: frozenset[MCPServer]) -> MCPServer | None:
    """Match a user-supplied name (lowercase enum value) to a candidate server."""
    for srv in candidates:
        if srv.value == name:
            return srv
    return None


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
        start_ui()
    except ImportError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
