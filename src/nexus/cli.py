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
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer
import yaml as _yaml
from packaging.version import InvalidVersion, parse
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Column, Table

from nexus.auth.external_keychain import ExternalKeychainClient
from nexus.cache import clear_cache
from nexus.capabilities.claude_config import FilesystemClaudeCodeConfigReader
from nexus.capabilities.feature_flags import claude_ai_name_for
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.status_reporter import StatusReporter
from nexus.capabilities.tier import TierDetection, TierDetector
from nexus.capture.engine import CaptureEngine
from nexus.capture.models import ArchiveManifest, ScopeEntry
from nexus.capture.tables import AI_AUTOMATION, DEFAULT_TABLE_GROUPS
from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths
from nexus.config.settings import InstancesConfig
from nexus.connectors.servicenow.client import ServiceNowClient
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
from nexus.ui.theme import NEXUS_THEME, SN_BLUE, SN_LIME
from nexus.updater import check_and_maybe_update, current_version
from nexus.updater.client import GitHubReleasesClient

__all__: list[str] = []

log = logging.getLogger(__name__)

app = typer.Typer(
    name="nexus",
    help="NEXUS -- ServiceNow AI architect agent",
    no_args_is_help=True,
)

instance_app = typer.Typer(name="instance", help="Manage ServiceNow instances.")
app.add_typer(instance_app)

capture_app = typer.Typer(name="capture", help="Capture and deploy ServiceNow configurations.")
app.add_typer(capture_app)

_CAPTURE_HELP = [
    ("discover [instance]", "List scopes with custom AI/automation configs"),
    ("pull [instance] --scope <key>", "Capture a scope to a YAML archive"),
    ("list [instance]", "Show local archives"),
    ("push <archive> [instance]", "Push an archive into an update set on the target"),
]

# Custom scope prefixes -- anything else is an OOTB ServiceNow application.
_CUSTOM_SCOPE_PREFIXES = ("x_", "u_")

_SCOPE_KEY_WIDTH = 26  # column width for scope key (the identifier users copy)
_SCOPE_NAME_WIDTH = 20  # column width for display name

# Short column header per table spec name -- wide enough to be readable, narrow to fit 80-col
_TABLE_HEADER: dict[str, str] = {
    "ai_skill": "Skl",
    "sys_hub_flow": "Flow",
    "sys_hub_action_type_definition": "Act",
    "virtual_agent_conversation_topic": "VA",
    "sys_ai_agent": "AI",
}

# Derived hex strings -- used throughout the capture UI layer.
_SN_BLUE_S = f"rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]})"
_SN_LIME_S = f"rgb({SN_LIME[0]},{SN_LIME[1]},{SN_LIME[2]})"


def _make_progress() -> Progress:
    return Progress(
        SpinnerColumn(style=_SN_BLUE_S),
        TextColumn(
            f"[{_SN_BLUE_S}]{{task.description}}",
            table_column=Column(min_width=50, no_wrap=True),
        ),
        BarColumn(bar_width=30, complete_style=_SN_LIME_S, finished_style=_SN_LIME_S),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )


def _trunc(s: str, width: int) -> str:
    """Truncate a string to width characters, appending ellipsis if needed."""
    return s if len(s) <= width else s[: width - 1] + "…"


def _count_cell(n: int) -> str:
    """Dim zero counts; SN lime for non-zero (positive/active)."""
    return "[dim]0[/dim]" if n == 0 else f"[{_SN_LIME_S}][bold]{n}[/bold][/{_SN_LIME_S}]"


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


def _resolve_profile(profile: str) -> tuple[InstanceRegistry, InstanceMeta]:
    """Resolve an optional profile to a registry and loaded meta.

    Args:
        profile: Profile name, or empty string to use the config default.

    Returns:
        Tuple of (registry, meta) for the resolved profile.

    Raises:
        SystemExit: Via typer.Exit if no default is set or the profile is not found.
    """
    if not profile:
        profile = _config_default()
    if not profile:
        err_console.print("No default instance set.")
        err_console.print("  Register one : nexus instance register <profile>")
        err_console.print("  Set default  : nexus instance use <profile>")
        err_console.print("  List all     : nexus instance")
        raise typer.Exit(1)
    registry = _instance_registry()
    try:
        return registry, registry.load(profile)
    except InstanceNotFoundError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc


def _oauth_for(profile: str, meta: InstanceMeta) -> SNOAuthClient:
    """Build an SNOAuthClient for a profile and its stored meta.

    Args:
        profile: Instance profile name.
        meta: InstanceMeta loaded from the registry.

    Returns:
        Configured SNOAuthClient.
    """
    return SNOAuthClient(
        profile=profile, url=meta.url, client_id=meta.client_id, username=meta.username
    )


def _set_default_profile(paths: NexusPaths, profile: str) -> None:
    """Persist profile as the default instance in config.

    Args:
        paths: NexusPaths for the current config root.
        profile: Profile name to set as default (empty string to clear).
    """
    manager = ConfigManager(paths)
    manager.save(manager.load().model_copy(update={"instances": InstancesConfig(default=profile)}))


def _detect_sn_version(url: str, token: str, profile: str) -> tuple[str, str, str]:
    """Query sys_properties to detect the SN version, build tag, and instance name.

    Tries glide.buildtag first; falls back to a LIKE search across all
    properties whose name contains 'buildtag' in case the exact key is absent.

    Args:
        url: Full instance URL.
        token: Valid Bearer token.
        profile: Fallback value for instance_name if the property is not found.

    Returns:
        Tuple of (sn_version, sn_build, instance_name). sn_version is
        'unknown' when the buildtag property is missing or unreadable.
    """
    sn_version = "unknown"
    sn_build = ""
    instance_name = profile
    try:
        with httpx.Client(
            base_url=url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        ) as client:
            _BUILDTAG_PROPS = ("glide.buildtag", "glide.buildtag.last")
            for prop in (*_BUILDTAG_PROPS, "instance_name"):
                if prop in _BUILDTAG_PROPS and sn_version != "unknown":
                    continue
                r = client.get(
                    "/api/now/table/sys_properties",
                    params={
                        "sysparm_query": f"name={prop}",
                        "sysparm_fields": "value",
                        "sysparm_limit": 1,
                    },
                )
                log.debug(
                    "version probe name=%s status=%d body=%.200s",
                    prop,
                    r.status_code,
                    r.text,
                )
                if r.status_code != 200:
                    continue
                rows = r.json().get("result", [])
                if not rows:
                    continue
                val = str(rows[0].get("value", "")).strip()
                if not val:
                    continue
                if prop in _BUILDTAG_PROPS:
                    sn_build = val
                    parts = val.split("-")
                    word = parts[1] if parts[0].lower() == "glide" and len(parts) > 1 else parts[0]
                    sn_version = word.capitalize()
                else:
                    instance_name = val

            if sn_version == "unknown":
                r = client.get(
                    "/api/now/table/sys_properties",
                    params={
                        "sysparm_query": "nameLIKEbuildtag",
                        "sysparm_fields": "name,value",
                        "sysparm_limit": 3,
                    },
                )
                log.debug("version fallback status=%d body=%.300s", r.status_code, r.text)
                if r.status_code == 200:
                    for row in r.json().get("result", []):
                        val = str(row.get("value", "")).strip()
                        if val:
                            sn_build = val
                            parts = val.split("-")
                            word = (
                                parts[1]
                                if parts[0].lower() == "glide" and len(parts) > 1
                                else parts[0]
                            )
                            sn_version = word.capitalize()
                            break

    except httpx.RequestError:
        pass
    return sn_version, sn_build, instance_name


def _print_oauth_setup(url: str, profile: str) -> None:
    """Print step-by-step manual OAuth setup instructions for ServiceNow.

    Args:
        url: Full instance URL, used to build the direct navigation link.
        profile: Profile alias, used as the suggested OAuth app name.
    """
    console.print("")
    console.print("  Manual OAuth setup (one-time, ~2 minutes):")
    console.print("")
    console.print(f"  1. Open {url} and navigate to:")
    console.print("       System OAuth > Application Registry > New")
    console.print("     Choose 'Create an OAuth API endpoint for external clients'")
    console.print("")
    console.print("  2. Fill in:")
    console.print(f"       Name          nexus-{profile}")
    console.print("       Redirect URL   https://localhost  (placeholder, not used)")
    console.print("     Click Submit.")
    console.print("")
    console.print("  3. Open the record you just created:")
    console.print("       Copy the Client ID  (UUID shown at the top of the form)")
    console.print("       Click the lock icon next to Client Secret to reveal it")
    console.print("     Paste both values below.")
    console.print("")


def _warn_token_cap(url: str, username: str, password: str) -> None:
    """Print a warning if the SN system access token cap is below 8 hours.

    The property glide.oauth.access_token.expire_in.system_max_seconds overrides
    the token_lifetime on any OAuth application. When it is set below 28800 (8h),
    access tokens expire sooner, but NEXUS auto-refreshes using the 90-day refresh
    token so this does not interrupt the user. The warning tells an admin how to
    raise the cap if they want longer access tokens.

    Args:
        url: Full instance URL.
        username: SN login for Basic auth.
        password: SN password for Basic auth.
    """
    _CAP_PROP = "glide.oauth.access_token.expire_in.system_max_seconds"
    try:
        with httpx.Client(base_url=url, timeout=10.0) as sn:
            r = sn.get(
                "/api/now/table/sys_properties",
                params={
                    "sysparm_query": f"name={_CAP_PROP}",
                    "sysparm_fields": "value",
                    "sysparm_limit": "1",
                },
                auth=(username, password),
            )
        if r.status_code != 200:
            return
        rows = r.json().get("result", [])
        if not rows:
            return
        cap = int(rows[0].get("value", "0"))
        if 0 < cap < 28800:
            console.print(f"  Note: SN system cap limits access tokens to {cap // 60} min.")
            console.print("  NEXUS auto-refreshes silently -- this will not interrupt your work.")
            console.print("  To set 8h tokens, an admin can run in a SN background script:")
            console.print(f"    gs.setProperty('{_CAP_PROP}', '28800');")
    except Exception:  # non-fatal -- registration already succeeded
        pass


def _provision_oauth(url: str, profile: str, username: str, password: str) -> tuple[str, str]:
    """Try to auto-create an OAuth app in SN; fall back to manual prompts on failure.

    Posts to the oauth_entity Table API using HTTP Basic auth. If the instance
    returns 201 with a client_id, the caller receives those credentials without
    any interactive prompts. On any failure the user is shown setup instructions
    and prompted to enter the credentials manually.

    Args:
        url: Full instance URL.
        profile: Profile alias used as the OAuth app name suffix.
        username: SN login for Basic auth.
        password: SN password for Basic auth.

    Returns:
        Tuple of (client_id, client_secret).
    """
    generated_secret = str(uuid.uuid4())
    fail_reason = ""
    try:
        with httpx.Client(base_url=url, timeout=10.0) as sn:
            resp = sn.post(
                "/api/now/table/oauth_entity",
                json={
                    "name": f"nexus-{profile}",
                    "type": "oauth2",
                    "client_secret": generated_secret,
                    "redirect_url": "https://localhost",
                    "token_lifetime": "28800",  # 8h -- may be overridden by SN system cap
                    "refresh_token_lifetime": "7776000",  # 90 days -- survives access token cap
                },
                auth=(username, password),
            )
        if resp.status_code == 201:
            result = resp.json().get("result", {})
            client_id = str(result.get("client_id", ""))
            if client_id:
                console.print(f"  Created OAuth application 'nexus-{profile}' automatically.")
                _warn_token_cap(url, username, password)
                return client_id, generated_secret
            fail_reason = "HTTP 201 but no client_id in response"
        else:
            fail_reason = f"HTTP {resp.status_code}"
    except httpx.RequestError as exc:
        fail_reason = str(exc)

    console.print(f"  Could not auto-create OAuth credentials ({fail_reason}).")
    _print_oauth_setup(url, profile)
    client_id = typer.prompt("  OAuth Client ID")
    client_secret: str = typer.prompt("  OAuth Client Secret", hide_input=True)
    return client_id, client_secret


def _acquire_token(
    profile: str,
) -> tuple[InstanceRegistry, InstanceMeta, str, datetime]:
    """Resolve profile, acquire bearer token, reconnecting automatically if expired.

    When both the access token and refresh token are expired, prompts the user
    for their ServiceNow password and re-authenticates transparently so the
    caller can continue without manual intervention.

    Args:
        profile: Instance profile name (empty string uses config default).

    Returns:
        (registry, meta, bearer_token, token_expiry)
    """
    registry, meta = _resolve_profile(profile)
    oauth = _oauth_for(meta.profile, meta)
    try:
        token, expiry = oauth.get_bearer_token(meta.token_expires_at)
        # Persist the refreshed expiry so nexus instance list shows the correct status.
        if expiry != meta.token_expires_at:
            registry.save(meta.model_copy(update={"token_expires_at": expiry}))
        return registry, meta, token, expiry
    except TokenExpiredError:
        console.print(f"Session expired for {meta.profile!r}. Reconnecting...")
    try:
        password: str = typer.prompt("ServiceNow password", hide_input=True)
        token, expiry = oauth.reconnect(password)
    except OAuthError as exc:
        err_console.print(f"Reconnect failed: {exc}")
        raise typer.Exit(1) from exc
    registry.save(meta.model_copy(update={"token_expires_at": expiry}))
    console.print(f"Reconnected. Token valid until {expiry.strftime('%H:%M UTC')}.")
    return registry, meta, token, expiry


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


_INSTANCE_HELP = [
    ("register <profile>", "Add an instance -- wizard prompts for URL, credentials"),
    ("connect [profile]", "Verify connectivity, refresh token if near expiry"),
    ("refresh [profile]", "Pull a fresh artifact snapshot"),
    ("status [profile]", "Show instance metadata and snapshot detail"),
    ("use <profile>", "Set the default instance (* marker)"),
    ("delete <profile>", "Remove an instance and its keychain entries"),
    ("list", "Show all instances in tabular form"),
]


@instance_app.callback(invoke_without_command=True)
def instance_callback(ctx: typer.Context) -> None:
    """Show registered instances and available commands."""
    if ctx.invoked_subcommand is not None:
        return

    if not _instance_registry().list_all():
        console.print("No instances registered.")
        console.print("")
        console.print("Quickstart:")
        console.print("  nexus instance register dev")
        console.print("")
        console.print("  You will be prompted for:")
        console.print("    Profile  -- already supplied above ('dev', 'prod', or any alias)")
        console.print("    Instance -- subdomain, FQDN, or full URL, e.g.:")
        console.print("                  dev12345")
        console.print("                  dev12345.service-now.com")
        console.print("                  https://dev12345.service-now.com")
        console.print("    Username -- your ServiceNow login (e.g. admin)")
        console.print("    Password -- your ServiceNow password (not stored)")
        console.print("")
        console.print("  NEXUS will auto-create OAuth credentials using your username and")
        console.print("  password. If auto-creation fails, you will be shown setup steps.")
        console.print("")
    else:
        instance_list()

    console.print("Commands:")
    for cmd, desc in _INSTANCE_HELP:
        console.print(f"  nexus instance {cmd:<25} {desc}")
    console.print("")
    console.print("Run 'nexus instance <command> --help' for usage details.")


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
    registry, meta = _resolve_profile(profile)

    now = datetime.now(UTC)
    remaining = (meta.token_expires_at - now).total_seconds() / 60
    token_str = f"valid ({int(remaining)} min remaining)" if remaining > 0 else "EXPIRED"

    console.print(f"Instance:  {meta.profile}")
    console.print(f"URL:       {meta.url}")
    console.print(f"Version:   {meta.sn_version} ({meta.sn_build})")
    console.print(f"Token:     {token_str}")
    console.print(f"Connected: {meta.last_connected_at.strftime('%Y-%m-%d %H:%M UTC')}")

    snapshot = registry.load_snapshot(meta.profile)
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

    registry, meta = _resolve_profile(profile)
    _oauth_for(profile, meta).delete_tokens()
    registry.delete(meta.profile)

    paths = NexusPaths.from_env()
    manager = ConfigManager(paths)
    cfg = manager.load()
    if cfg.instances.default == profile:
        manager.save(cfg.model_copy(update={"instances": InstancesConfig(default="")}))

    console.print(f"Deleted instance {profile!r}.")


@instance_app.command("use")
def instance_use(profile: str) -> None:
    """Set the default instance."""
    _resolve_profile(profile)
    _set_default_profile(NexusPaths.from_env(), profile)
    console.print(f"Default instance set to {profile!r}.")


@instance_app.command("connect")
def instance_connect(profile: str = typer.Argument("")) -> None:
    """Verify connectivity and refresh token if near expiry."""
    registry, meta, token, new_expiry = _acquire_token(profile)
    profile = meta.profile

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
    sn_version, sn_build, instance_name = _detect_sn_version(meta.url, token, meta.profile)
    update: dict[str, object] = {"last_connected_at": now, "token_expires_at": new_expiry}
    if sn_version != "unknown":
        update["sn_version"] = sn_version
        update["sn_build"] = sn_build
        update["instance_name"] = instance_name
    registry.save(meta.model_copy(update=update))
    console.print(
        f"Connected to {profile!r}. Token valid until {new_expiry.strftime('%H:%M UTC')}."
    )


@instance_app.command("refresh")
def instance_refresh(profile: str = typer.Argument("")) -> None:
    """Pull a fresh artifact snapshot from the instance."""
    registry, meta, token, new_expiry = _acquire_token(profile)
    profile = meta.profile

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

    console.print(f"Registering instance '{profile}'")
    console.print(f"  '{profile}' is your local alias -- use it in all nexus instance commands.")
    console.print("")
    raw_url: str = typer.prompt("  Instance (subdomain, FQDN, or https:// URL -- e.g. dev12345)")
    host = raw_url.removeprefix("https://").removeprefix("http://").rstrip("/")
    if "." not in host:
        host = f"{host}.service-now.com"
    url = f"https://{host}"
    username: str = typer.prompt("  Username")
    password: str = typer.prompt("  Password", hide_input=True)

    client_id, client_secret = _provision_oauth(url, profile, username, password)

    console.print("  Exchanging credentials for OAuth token...")
    oauth = SNOAuthClient(profile=profile, url=url, client_id=client_id, username=username)
    try:
        token_response = oauth.exchange(client_secret, password)
    except OAuthError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1) from exc

    sn_version, sn_build, instance_name = _detect_sn_version(
        url, token_response.access_token, profile
    )
    if sn_version == "unknown":
        console.print(
            "  Version: unknown (glide.buildtag not in sys_properties -- "
            "run with --log-level DEBUG to diagnose)"
        )

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

    if not ConfigManager(paths).load().instances.default:
        _set_default_profile(paths, profile)
        console.print("  Set as default instance.")


@capture_app.callback(invoke_without_command=True)
def capture_callback(ctx: typer.Context) -> None:
    """Show local archives and available commands."""
    if ctx.invoked_subcommand is not None:
        return
    capture_list()
    console.print()
    console.print(f"  [{_SN_BLUE_S}]Commands[/{_SN_BLUE_S}]")
    for cmd, desc in _CAPTURE_HELP:
        console.print(
            f"  [{_SN_BLUE_S}]nexus capture[/{_SN_BLUE_S}]"
            f" [white]{cmd:<40}[/white]"
            f" [dim]{desc}[/dim]"
        )
    console.print()
    console.print("  [dim]Run [bold]nexus capture <command> --help[/bold] for details.[/dim]")


@capture_app.command("discover")
def capture_discover(
    instance: Annotated[
        str, typer.Argument(help="Instance profile name (default: configured default)")
    ] = "",
    group: Annotated[str, typer.Option(help="Table group")] = AI_AUTOMATION.key,
    all_scopes: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Show all scopes, not just your custom ones (x_*, u_*)",
        ),
    ] = False,
) -> None:
    """Discover which of your scopes have custom AI/automation configs."""

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        resolved = instance or _config_default()

        with _make_progress() as progress:
            task = progress.add_task(f"Connecting to {resolved}...", total=None)

            def on_progress(completed: int, total: int, message: str) -> None:
                progress.update(
                    task,
                    description=message,
                    total=total if total > 0 else None,
                    completed=completed,
                )

            async with client:
                manifest = await engine.discover_scopes(resolved, group, on_progress=on_progress)

        if not manifest.scopes:
            console.print("No scopes with custom configurations found.")
            return

        all_s = list(manifest.scopes)
        custom_s = [s for s in all_s if s.scope.startswith(_CUSTOM_SCOPE_PREFIXES)]

        # Sort: custom scopes first (by total count desc), then rest by total count desc
        def _total(s: ScopeEntry) -> int:
            return sum(s.table_counts.values())

        custom_s.sort(key=_total, reverse=True)
        rest_s = [s for s in all_s if not s.scope.startswith(_CUSTOM_SCOPE_PREFIXES)]
        rest_s.sort(key=_total, reverse=True)

        display = all_s if all_scopes else (custom_s if custom_s else all_s)

        group_obj = DEFAULT_TABLE_GROUPS.get(group)
        tbl = Table(
            show_header=True,
            header_style="bold",
            box=None,
            pad_edge=False,
            show_edge=False,
        )
        tbl.add_column(
            "Scope Key",
            style=_SN_BLUE_S,
            no_wrap=True,
            width=_SCOPE_KEY_WIDTH,
        )
        tbl.add_column("Name", style="white", no_wrap=True, width=_SCOPE_NAME_WIDTH)
        if group_obj:
            for spec in group_obj.tables:
                hdr = _TABLE_HEADER.get(spec.name, spec.display[:4])
                tbl.add_column(hdr, justify="right", no_wrap=True, width=5)

        for scope in display:
            row: list[str] = [
                _trunc(scope.scope, _SCOPE_KEY_WIDTH),
                _trunc(scope.name, _SCOPE_NAME_WIDTH),
            ]
            if group_obj:
                for spec in group_obj.tables:
                    row.append(_count_cell(scope.table_counts.get(spec.name, 0)))
            tbl.add_row(*row)

        console.print()
        console.print(tbl)
        console.print()

        # Summary line
        if all_scopes or not custom_s:
            console.print(f"  [dim]{len(display)} scopes with custom configs on {resolved}[/dim]")
        else:
            console.print(
                f"  [dim]Showing {len(custom_s)} of your custom scopes"
                f" ({len(all_s)} total with configs)."
                f"  Use [bold]--all[/bold] to show all.[/dim]"
            )

        # Next step hint -- SN blue label, white command
        if display:
            example = display[0].scope
            console.print()
            console.print(
                f"  [{_SN_LIME_S}]Next:[/{_SN_LIME_S}]"
                f" [bold white]nexus capture pull --scope {example}[/bold white]"
            )
            if len(display) > 1:
                console.print(
                    "  [dim]Use --scope multiple times to capture several scopes at once.[/dim]"
                )

    asyncio.run(_run())


_UUID_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


async def _resolve_scope_ids(
    scope_args: list[str],
    engine: CaptureEngine,
    client: ServiceNowClient,
    instance_id: str,
    group: str,
) -> list[str]:
    """Resolve scope keys (x_snc_*) or sys_ids to sys_ids.

    If the arg is a 32-hex-char UUID it is used as-is.
    Otherwise it is treated as a scope key and looked up via discover.
    """
    keys_to_lookup = [s for s in scope_args if not _UUID_RE.match(s.replace("-", ""))]

    if not keys_to_lookup:
        return scope_args

    # Discover to get the key -> sys_id mapping
    with _make_progress() as progress:
        task = progress.add_task("Resolving scope keys...", total=None)

        def _prog(completed: int, total: int, message: str) -> None:
            progress.update(task, description=message, total=total or None, completed=completed)

        async with client:
            manifest = await engine.discover_scopes(instance_id, group, on_progress=_prog)

    key_map = {s.scope: s.sys_id for s in manifest.scopes}
    resolved: list[str] = []
    for arg in scope_args:
        if _UUID_RE.match(arg.replace("-", "")):
            resolved.append(arg)
        elif arg in key_map:
            resolved.append(key_map[arg])
            console.print(f"  Resolved [cyan]{arg}[/cyan] -> {key_map[arg]}")
        else:
            err_console.print(
                f"Scope {arg!r} not found. Run 'nexus capture discover' to see available scopes."
            )
            raise typer.Exit(1)
    return resolved


@capture_app.command("pull")
def capture_pull(
    instance: Annotated[
        str, typer.Argument(help="Instance profile name (default: configured default)")
    ] = "",
    scope: Annotated[
        list[str],
        typer.Option(help="Scope key (e.g. x_snc_my_app) or sys_id -- repeatable, from 'discover'"),
    ] = [],
    group: Annotated[str, typer.Option(help="Table group")] = AI_AUTOMATION.key,
) -> None:
    """Capture custom configurations for one or more scopes to a local archive.

    Run 'nexus capture discover' first to see scope keys.
    """
    if not scope:
        err_console.print("At least one --scope is required.")
        err_console.print("  Run 'nexus capture discover' to see your scope keys.")
        raise typer.Exit(1)

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        resolved_instance = instance or _config_default()

        # Resolve any scope keys to sys_ids (re-uses the same client)
        scope_ids = await _resolve_scope_ids(scope, engine, client, resolved_instance, group)

        with _make_progress() as progress:
            task = progress.add_task("Preparing...", total=None)

            def on_progress(completed: int, total: int, message: str) -> None:
                progress.update(
                    task,
                    description=message,
                    total=total if total > 0 else None,
                    completed=completed,
                )

            async with client:
                result = await engine.capture(
                    resolved_instance, scope_ids, group, on_progress=on_progress
                )

        manifest = engine.save_archive(result)
        console.print()
        console.print(
            f"  [{_SN_LIME_S}][bold]{manifest.record_count} records captured[/bold][/{_SN_LIME_S}]"
        )
        console.print(f"  [dim]Archive:[/dim] [white]{manifest.archive_dir}[/white]")
        console.print()
        console.print(
            f"  [{_SN_LIME_S}]Next:[/{_SN_LIME_S}]"
            f" [bold white]nexus capture push {manifest.archive_dir}[/bold white]"
        )

    asyncio.run(_run())


@capture_app.command("list")
def capture_list(
    instance: Annotated[str | None, typer.Argument(help="Filter by instance")] = None,
) -> None:
    """List local capture archives."""
    archives_root = NexusPaths.from_env().archives_dir
    if not archives_root.exists():
        console.print("No archives found.")
        return

    tbl = Table(title="Local Archives")
    tbl.add_column("Instance")
    tbl.add_column("Timestamp")
    tbl.add_column("Records", justify="right")
    tbl.add_column("Path")

    for manifest_path in sorted(archives_root.rglob("manifest.yaml")):
        try:
            raw = _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest = ArchiveManifest.model_validate(raw, strict=False)
        except Exception as exc:
            err_console.print(f"Skipping corrupt manifest {manifest_path.parent}: {exc}")
            continue
        if instance and manifest.instance_id != instance:
            continue
        tbl.add_row(
            manifest.instance_id,
            str(manifest.captured_at)[:19],
            str(manifest.record_count),
            str(manifest.archive_dir),
        )
    console.print(tbl)


@capture_app.command("push")
def capture_push(
    archive: Annotated[str, typer.Argument(help="Path to archive directory")],
    instance: Annotated[
        str, typer.Argument(help="Target instance profile (default: configured default)")
    ] = "",
    update_set: Annotated[str, typer.Option(help="Update set name")] = "NEXUS-capture",
) -> None:
    """Push a local archive into an update set on the target instance."""

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        manifest_path = Path(archive) / "manifest.yaml"
        result = engine.load_archive(manifest_path)
        async with client:
            ref = await engine.push_to_update_set(result, instance, update_set)
        console.print(f"Injected {ref.record_count} records into update set {ref.name!r}.")
        console.print(f"Update set sys_id: {ref.sys_id}")

    asyncio.run(_run())


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
