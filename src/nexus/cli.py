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
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer
import yaml as _yaml
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
from nexus.capture.engine import CaptureEngine
from nexus.capture.models import ArchiveManifest
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

capture_app = typer.Typer(name="capture", help="Capture and deploy ServiceNow configurations.")
app.add_typer(capture_app)

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
        with httpx.Client(base_url=url, timeout=10.0) as client:
            resp = client.post(
                "/api/now/table/oauth_entity",
                json={
                    "name": f"nexus-{profile}",
                    "type": "oauth2",
                    "client_secret": generated_secret,
                    "redirect_url": "https://localhost",
                    "token_lifetime": "28800",
                },
                auth=(username, password),
            )
        if resp.status_code == 201:
            result = resp.json().get("result", {})
            client_id = str(result.get("client_id", ""))
            if client_id:
                console.print(f"  Created OAuth application 'nexus-{profile}' automatically.")
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


def _build_capture_engine(profile: str) -> tuple[CaptureEngine, ServiceNowClient]:
    """Build a CaptureEngine for the given registered instance profile.

    Gets the OAuth bearer token for the profile and constructs both a
    ServiceNowClient (used as an async context manager by callers) and a
    CaptureEngine wired to the same client.

    Args:
        profile: Instance profile name from InstanceRegistry.

    Returns:
        Tuple of (CaptureEngine, ServiceNowClient). The caller must use the
        client as an async context manager before awaiting engine methods.

    Raises:
        typer.Exit: With code 1 if the profile is not registered or the
            OAuth token is expired.
    """
    _, meta = _resolve_profile(profile)
    oauth = _oauth_for(profile, meta)
    try:
        token, _ = oauth.get_bearer_token(meta.token_expires_at)
    except TokenExpiredError as exc:
        err_console.print(str(exc))
        err_console.print("  Refresh the token: nexus instance connect")
        raise typer.Exit(1) from exc
    client = ServiceNowClient(
        instance_url=meta.url,
        username=meta.username,
        password=token,
    )
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
    registry, meta = _resolve_profile(profile)
    profile = meta.profile
    oauth = _oauth_for(profile, meta)
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
    registry, meta = _resolve_profile(profile)
    profile = meta.profile
    oauth = _oauth_for(profile, meta)
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


@capture_app.command("discover")
def capture_discover(
    instance: Annotated[str, typer.Argument(help="Instance profile name")],
    group: Annotated[str, typer.Option(help="Table group")] = AI_AUTOMATION.key,
) -> None:
    """Discover application scopes on an instance and show per-table counts."""

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        async with client:
            manifest = await engine.discover_scopes(instance, group)

        if not manifest.scopes:
            console.print("No application scopes found.")
            return

        tbl = Table(title=f"Scopes on {instance}")
        tbl.add_column("Name")
        tbl.add_column("Scope Key")
        group_obj = DEFAULT_TABLE_GROUPS.get(group)
        if group_obj:
            for spec in group_obj.tables:
                tbl.add_column(spec.display, justify="right")
        for scope in manifest.scopes:
            row = [scope.name, scope.scope]
            if group_obj:
                for spec in group_obj.tables:
                    row.append(str(scope.table_counts.get(spec.name, 0)))
            tbl.add_row(*row)
        console.print(tbl)

    asyncio.run(_run())


@capture_app.command("pull")
def capture_pull(
    instance: Annotated[str, typer.Argument(help="Instance profile name")],
    scope: Annotated[list[str], typer.Option(help="Scope sys_id (repeatable)")],
    group: Annotated[str, typer.Option(help="Table group")] = AI_AUTOMATION.key,
) -> None:
    """Capture custom configurations for selected scopes to a local archive."""

    async def _run() -> None:
        engine, client = _build_capture_engine(instance)
        async with client:
            result = await engine.capture(instance, scope, group)
        manifest = engine.save_archive(result)
        console.print(f"Captured {manifest.record_count} records.")
        console.print(f"Archive: {manifest.archive_dir}")

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
    instance: Annotated[str, typer.Argument(help="Target instance profile")],
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
