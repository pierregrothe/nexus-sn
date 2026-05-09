# nexus/cli.py
# Typer CLI entry point for NEXUS.
# Author: Pierre Grothe
# Date: 2026-05-07

"""NEXUS command-line interface.

All commands validate config and credentials at startup.
Features requiring unavailable MCP servers are hidden from help text.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated

import httpx
import typer
from packaging.version import InvalidVersion, parse
from rich.console import Console
from rich.table import Table

from nexus.auth.external_keychain import ExternalKeychainClient
from nexus.cache import clear_cache
from nexus.capabilities.claude_config import FilesystemClaudeCodeConfigReader
from nexus.capabilities.feature_flags import claude_ai_name_for
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.status_reporter import StatusReporter
from nexus.capabilities.tier import TierDetection, TierDetector
from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths
from nexus.config.settings import InstancesConfig
from nexus.instances.errors import (
    InstanceNotFoundError,
    OAuthError,
    SnapshotError,
    TokenExpiredError,
)
from nexus.instances.models import InstanceMeta
from nexus.instances.oauth import SNOAuthClient
from nexus.instances.registry import InstanceRegistry
from nexus.instances.scanner import InstanceScanner
from nexus.ui.app import start_ui
from nexus.ui.banner import print_banner
from nexus.ui.theme import NEXUS_THEME
from nexus.updater import check_and_maybe_update, current_version
from nexus.updater.client import GitHubReleasesClient

log = logging.getLogger(__name__)

app = typer.Typer(
    name="nexus",
    help="NEXUS -- ServiceNow AI architect agent",
    no_args_is_help=True,
)

instance_app = typer.Typer(name="instance", help="Manage ServiceNow instances.")
app.add_typer(instance_app)

console = Console(theme=NEXUS_THEME)
err_console = Console(stderr=True, theme=NEXUS_THEME)


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
    check_and_maybe_update()


@app.command()
def setup() -> None:
    """First-run wizard: configure credentials, instances, and sync templates."""
    console.print("[bold]NEXUS Setup[/bold]")
    console.print("Interactive setup wizard -- not yet implemented.")
    console.print("Configure manually by editing ~/.nexus/config.yaml")


def _detect_tier() -> TierDetection:
    """Run tier detection using a Claude-Code-aware keychain reader."""
    reader = FilesystemClaudeCodeConfigReader(keychain=ExternalKeychainClient())
    return TierDetector(reader=reader).detect()


def _instance_registry() -> InstanceRegistry:
    """Return an InstanceRegistry rooted at the current config path.

    Returns:
        InstanceRegistry for NexusPaths.from_env().instances_dir.
    """
    return InstanceRegistry(NexusPaths.from_env().instances_dir)


def _config_default() -> str:
    """Return the default instance profile from config.

    Returns:
        Profile name string, or empty string if not set.
    """
    return ConfigManager(NexusPaths.from_env()).load().instances.default


@instance_app.command("list")
def instance_list() -> None:
    """Show all registered ServiceNow instances."""
    registry = _instance_registry()
    metas = registry.list_all()
    if not metas:
        console.print("No instances registered. Run 'nexus instance register <profile>'.")
        return

    default = _config_default()
    tbl = Table("Profile", "URL", "Version", "Token", "Last Connected")
    for meta in metas:
        now = datetime.now(UTC)
        if now >= meta.token_expires_at:
            token_str = "EXPIRED"
        else:
            mins = int((meta.token_expires_at - now).total_seconds() / 60)
            token_str = f"{mins} min left"
        prefix = "* " if meta.profile == default else "  "
        tbl.add_row(
            f"{prefix}{meta.profile}",
            meta.url,
            meta.sn_version,
            token_str,
            meta.last_connected_at.strftime("%Y-%m-%d %H:%M UTC"),
        )
    console.print(tbl)


@instance_app.command("status")
def instance_status(profile: str = typer.Argument("")) -> None:
    """Show metadata and snapshot summary for an instance."""
    if not profile:
        profile = _config_default()
    if not profile:
        err_console.print(
            "No default instance. Pass a profile or run 'nexus instance use <profile>'."
        )
        raise typer.Exit(1)

    registry = _instance_registry()
    try:
        meta = registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc

    now = datetime.now(UTC)
    remaining = (meta.token_expires_at - now).total_seconds() / 60
    token_str = f"valid ({int(remaining)} min remaining)" if remaining > 0 else "EXPIRED"

    console.print(f"Instance:  {meta.profile}")
    console.print(f"URL:       {meta.url}")
    console.print(f"Version:   {meta.sn_version} ({meta.sn_build})")
    console.print(f"Token:     {token_str}")
    console.print(f"Connected: {meta.last_connected_at.strftime('%Y-%m-%d %H:%M UTC')}")

    snapshot = registry.load_snapshot(profile)
    if snapshot is None:
        console.print("\nNo snapshot. Run 'nexus instance refresh' to capture one.")
        return

    c = snapshot.counts
    custom_flows = sum(1 for f in snapshot.flows if f.is_custom)
    custom_brs = sum(1 for r in snapshot.business_rules if r.is_custom)
    custom_sis = sum(1 for s in snapshot.script_includes if s.is_custom)
    console.print(f"\nSnapshot ({snapshot.captured_at.strftime('%Y-%m-%d %H:%M UTC')}):")
    console.print(f"  AI Skills:        {c.ai_skills}")
    console.print(f"  Flows:           {c.flows}  ({custom_flows} custom)")
    console.print(f"  Business Rules:  {c.business_rules}  ({custom_brs} custom)")
    console.print(f"  Script Includes: {c.script_includes}  ({custom_sis} custom)")


@instance_app.command("delete")
def instance_delete(
    profile: str,
    force: Annotated[bool, typer.Option("--force", help="Skip confirmation")] = False,
) -> None:
    """Remove a registered instance and its keychain entries."""
    if not force:
        if not typer.confirm(f"Delete instance {profile!r} and all its data?"):
            raise typer.Abort()

    registry = _instance_registry()
    try:
        meta = registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc

    SNOAuthClient(
        profile=profile, url=meta.url, client_id=meta.client_id, username=meta.username
    ).delete_tokens()
    registry.delete(profile)

    paths = NexusPaths.from_env()
    manager = ConfigManager(paths)
    cfg = manager.load()
    if cfg.instances.default == profile:
        manager.save(cfg.model_copy(update={"instances": InstancesConfig(default="")}))

    console.print(f"Deleted instance {profile!r}.")


@instance_app.command("use")
def instance_use(profile: str) -> None:
    """Set the default instance."""
    registry = _instance_registry()
    try:
        registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc

    paths = NexusPaths.from_env()
    manager = ConfigManager(paths)
    manager.save(manager.load().model_copy(update={"instances": InstancesConfig(default=profile)}))
    console.print(f"Default instance set to {profile!r}.")


@instance_app.command("connect")
def instance_connect(profile: str = typer.Argument("")) -> None:
    """Verify connectivity and refresh token if near expiry."""
    if not profile:
        profile = _config_default()
    if not profile:
        err_console.print("No default instance set.")
        raise typer.Exit(1)

    registry = _instance_registry()
    try:
        meta = registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc

    oauth = SNOAuthClient(
        profile=profile, url=meta.url, client_id=meta.client_id, username=meta.username
    )
    try:
        token, new_expiry = oauth.get_bearer_token(meta.token_expires_at)
    except TokenExpiredError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc

    try:
        with httpx.Client(
            base_url=meta.url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        ) as client:
            resp = client.get("/api/now/table/sys_properties", params={"sysparm_limit": 1})
        if resp.status_code != 200:
            err_console.print(f"Probe failed: HTTP {resp.status_code}")
            raise typer.Exit(1)
    except httpx.RequestError as exc:
        err_console.print(f"Cannot reach {meta.url}: {exc}")
        raise typer.Exit(1) from exc

    now = datetime.now(UTC)
    registry.save(
        meta.model_copy(update={"last_connected_at": now, "token_expires_at": new_expiry})
    )
    console.print(
        f"Connected to {profile!r}. Token valid until {new_expiry.strftime('%H:%M UTC')}."
    )


@instance_app.command("refresh")
def instance_refresh(profile: str = typer.Argument("")) -> None:
    """Pull a fresh artifact snapshot from the instance."""
    if not profile:
        profile = _config_default()
    if not profile:
        err_console.print("No default instance set.")
        raise typer.Exit(1)

    registry = _instance_registry()
    try:
        meta = registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc

    oauth = SNOAuthClient(
        profile=profile, url=meta.url, client_id=meta.client_id, username=meta.username
    )
    try:
        token, new_expiry = oauth.get_bearer_token(meta.token_expires_at)
    except TokenExpiredError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc

    console.print(f"Capturing snapshot from {profile!r}...")
    try:
        snapshot = asyncio.run(InstanceScanner().scan(meta.url, token, meta.sn_version))
    except SnapshotError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc

    registry.save_snapshot(profile, snapshot)
    c = snapshot.counts
    registry.save(meta.model_copy(update={"token_expires_at": new_expiry, "snapshot_counts": c}))
    console.print(
        f"Snapshot captured: {c.ai_skills} AI skills, {c.flows} flows, "
        f"{c.business_rules} business rules, {c.script_includes} script includes."
    )


@instance_app.command("register")
def instance_register(profile: str) -> None:
    """Interactive wizard to register a new ServiceNow instance via OAuth2."""
    paths = NexusPaths.from_env()
    if (paths.instances_dir / profile).exists():
        err_console.print(
            f"Profile {profile!r} already exists. "
            f"Delete it first with 'nexus instance delete {profile}'."
        )
        raise typer.Exit(1)

    console.print(f"Registering instance: {profile}")
    raw_url: str = typer.prompt("  Instance URL (e.g. dev12345.service-now.com)")
    stripped = raw_url.removeprefix("https://").removeprefix("http://")
    url = f"https://{stripped}"
    username: str = typer.prompt("  Username")
    client_id: str = typer.prompt("  OAuth Client ID")
    client_secret: str = typer.prompt("  OAuth Client Secret", hide_input=True)
    password: str = typer.prompt("  Password", hide_input=True)

    console.print("  Exchanging credentials for OAuth token...")
    oauth = SNOAuthClient(profile=profile, url=url, client_id=client_id, username=username)
    try:
        token_response = oauth.exchange(client_secret, password)
    except OAuthError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc

    sn_version = "unknown"
    sn_build = ""
    instance_name = profile
    try:
        with httpx.Client(
            base_url=url,
            headers={"Authorization": f"Bearer {token_response.access_token}"},
            timeout=10.0,
        ) as client:
            resp = client.get(
                "/api/now/table/sys_properties",
                params={
                    "sysparm_query": "nameINglide.buildtag,instance_name",
                    "sysparm_fields": "name,value",
                    "sysparm_limit": 2,
                },
            )
        if resp.status_code == 200:
            for row in resp.json().get("result", []):
                if row.get("name") == "glide.buildtag":
                    sn_build = str(row.get("value", ""))
                    sn_version = sn_build.split("-")[0] if sn_build else "unknown"
                elif row.get("name") == "instance_name":
                    instance_name = str(row.get("value", profile))
    except httpx.RequestError:
        pass

    registry = InstanceRegistry(paths.instances_dir)
    meta = InstanceMeta.create(
        profile=profile,
        url=url,
        username=username,
        client_id=client_id,
        sn_version=sn_version,
        sn_build=sn_build,
        instance_name=instance_name,
        token_expires_in=token_response.expires_in,
    )
    registry.register(meta)
    console.print(f"  Registered {profile} ({sn_version}).")

    manager = ConfigManager(paths)
    if not manager.load().instances.default:
        manager.save(
            manager.load().model_copy(update={"instances": InstancesConfig(default=profile)})
        )
        console.print("  Set as default instance.")


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
    detection = _detect_tier()

    if server is not None:
        target = next((srv for srv in detection.needs_reauth_servers if srv.value == server), None)
        if target is None:
            err_console.print(
                f"[error]Server {server!r} is not currently flagged for re-auth.[/error] "
                "Run `nexus status --refresh` if you think this is wrong."
            )
            raise typer.Exit(code=1)
        console.print(f'claude /mcp "{claude_ai_name_for(target)}"')
        return

    if not detection.needs_reauth_servers:
        console.print("All MCP servers authenticated. Nothing to do.")
        return

    for srv in sorted(detection.needs_reauth_servers, key=lambda s: s.value):
        console.print(f'  {srv.value}: claude /mcp "{claude_ai_name_for(srv)}"')


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
        console.print("nexus-sn is not installed as a distribution; cannot check.")
        return

    info = GitHubReleasesClient().fetch_latest()
    if info is None:
        console.print("Could not reach GitHub. No update info available.")
        return

    try:
        if parse(info.tag_name) <= parse(current):
            console.print(f"Up to date ({current})")
            return
    except InvalidVersion:
        console.print(f"Latest tag {info.tag_name!r} is not a valid version; skipping")
        return

    console.print(f"Update available: {current} -> {info.tag_name}")


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
        err_console.print(f"[error]{exc}[/error]")
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
