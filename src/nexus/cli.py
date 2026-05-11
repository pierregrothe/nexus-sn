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
from rich.console import Console, RenderableType
from rich.text import Text

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
from nexus.instances.badges import token_badge
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
from nexus.ui import (
    CommandGuide,
    DataColumn,
    DataTable,
    Hint,
    KeyValuePanel,
    KvRow,
    Notice,
    default_marker,
    nexus_progress,
)
from nexus.ui.app import start_ui
from nexus.ui.banner import print_banner
from nexus.ui.theme import NEXUS_THEME
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
    ("discover", "List scopes with custom AI/automation configs"),
    ("pull --scope <key>", "Capture a scope to a YAML archive"),
    ("list", "Show local archives"),
    ("push <archive>", "Push an archive into an update set"),
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


def _trunc(s: str, width: int) -> str:
    """Truncate ``s`` to ``width`` characters, appending an ellipsis if needed.

    Args:
        s: Source string.
        width: Maximum width including the ellipsis.

    Returns:
        ``s`` unchanged if its length fits, otherwise the first ``width - 3``
        characters followed by ``"..."``.
    """
    return s if len(s) <= width else s[: width - 3] + "..."


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


def _fetch_existing_nexus_oauth_apps(
    url: str, username: str, password: str
) -> list[dict[str, str]]:
    """Return oauth_entity records whose name starts with ``nexus-``.

    Lists OAuth applications already provisioned on the SN instance (e.g. by
    another Nexus install registered against the same instance). Returns ``[]``
    on any failure -- the caller treats that as 'no existing apps'.

    Args:
        url: Full instance URL.
        username: SN login for Basic auth.
        password: SN password for Basic auth.

    Returns:
        Each entry has keys ``name``, ``client_id``, ``sys_id``, ``sys_created_on``.
        Entries without a ``client_id`` are dropped.
    """
    try:
        with httpx.Client(base_url=url, timeout=10.0) as sn:
            resp = sn.get(
                "/api/now/table/oauth_entity",
                params={
                    "sysparm_query": "nameSTARTSWITHnexus-",
                    "sysparm_fields": "name,client_id,sys_id,sys_created_on",
                    "sysparm_limit": "100",
                },
                auth=(username, password),
            )
        if resp.status_code != 200:
            return []
        rows = resp.json().get("result", [])
        return [
            {
                "name": str(r.get("name", "")),
                "client_id": str(r.get("client_id", "")),
                "sys_id": str(r.get("sys_id", "")),
                "sys_created_on": str(r.get("sys_created_on", "")),
            }
            for r in rows
            if r.get("client_id")
        ]
    except httpx.RequestError, ValueError:
        return []


def _pick_existing_oauth_app(entries: list[dict[str, str]], profile: str) -> tuple[str, str] | None:
    """Prompt the user to reuse an existing Nexus OAuth app or create a new one.

    The client_secret is not retrievable from ServiceNow (the Table API returns
    a masked value), so the user must paste it from the other Nexus install
    that originally provisioned the app.

    Args:
        entries: Output of ``_fetch_existing_nexus_oauth_apps``. Must be non-empty.
        profile: Profile being registered -- shown in the "create new" option.

    Returns:
        ``(client_id, client_secret)`` if the user picks an existing entry and
        supplies the secret, or ``None`` if they choose to create a new app.
    """
    console.print("")
    console.print(f"  Found {len(entries)} existing Nexus OAuth app(s) on this instance:")
    for i, entry in enumerate(entries, 1):
        console.print(
            f"    {i}. {entry['name']}  "
            f"(client_id={entry['client_id']}, created {entry['sys_created_on']})"
        )
    console.print(f"    n. Create a new app named 'nexus-{profile}'")
    console.print("")
    raw: str = typer.prompt(f"  Pick one (1-{len(entries)}) or 'n' for new")
    choice = raw.strip().lower()
    if choice == "n":
        return None
    try:
        idx = int(choice)
    except ValueError:
        console.print(f"  Invalid choice {raw!r}; will create a new app.")
        return None
    if not 1 <= idx <= len(entries):
        console.print(f"  Choice {idx} out of range; will create a new app.")
        return None
    picked = entries[idx - 1]
    console.print(f"  Reusing OAuth app '{picked['name']}' (client_id={picked['client_id']}).")
    console.print(
        "  The client secret is not readable from ServiceNow -- "
        "paste it from your other Nexus install."
    )
    secret: str = typer.prompt("  OAuth Client Secret", hide_input=True)
    return picked["client_id"], secret


def _provision_oauth(url: str, profile: str, username: str, password: str) -> tuple[str, str]:
    """Reuse or auto-create an OAuth app in SN; fall back to manual prompts on failure.

    First queries the instance for any existing ``nexus-*`` OAuth apps and, if
    found, offers to reuse one (prompting the user for its client_secret since
    SN won't return it). If the user declines or no entry is found, POSTs a new
    record to the oauth_entity Table API using HTTP Basic auth. On any failure
    the user is shown setup instructions and prompted to enter the credentials
    manually.

    Args:
        url: Full instance URL.
        profile: Profile alias used as the OAuth app name suffix.
        username: SN login for Basic auth.
        password: SN password for Basic auth.

    Returns:
        Tuple of (client_id, client_secret).
    """
    existing = _fetch_existing_nexus_oauth_apps(url, username, password)
    if existing:
        picked = _pick_existing_oauth_app(existing, profile)
        if picked is not None:
            return picked

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
    ("register <profile>", "Add an instance (wizard: URL, credentials)"),
    ("connect [profile]", "Verify connection and refresh token"),
    ("refresh [profile]", "Pull a fresh artifact snapshot"),
    ("status [profile]", "Show metadata and snapshot detail"),
    ("use <profile>", "Set as the default instance"),
    ("delete <profile>", "Remove an instance and its credentials"),
    ("list", "Show all registered instances"),
]


@instance_app.callback(invoke_without_command=True)
def instance_callback(ctx: typer.Context) -> None:
    """Show registered instances and available commands."""
    if ctx.invoked_subcommand is not None:
        return

    if not _instance_registry().list_all():
        console.print()
        console.print(
            Hint(
                label="Get started",
                command="nexus instance register dev",
                suffix="(you will be prompted for URL, username, password)",
            )
        )
        console.print()
    else:
        instance_list()

    console.print(CommandGuide(app_name="nexus instance", items=_INSTANCE_HELP))


@instance_app.command("list")
def instance_list() -> None:
    """Show all registered ServiceNow instances."""
    registry = _instance_registry()
    metas = registry.list_all()
    if not metas:
        console.print(
            Hint(
                label="No instances registered",
                command="nexus instance register <profile>",
            )
        )
        return

    default = _config_default()
    rows: list[list[RenderableType]] = []
    for meta in metas:
        profile_cell = Text()
        if meta.profile == default:
            profile_cell.append_text(default_marker())
        else:
            profile_cell.append("  ")
        profile_cell.append(meta.profile)
        rows.append(
            [
                profile_cell,
                _trunc(meta.url.replace("https://", ""), 36),
                meta.sn_version,
                token_badge(meta),
                meta.last_connected_at.strftime("%Y-%m-%d %H:%M"),
            ]
        )
    console.print(
        DataTable(
            title="Instances",
            columns=[
                DataColumn(header="Profile", width=14),
                DataColumn(header="URL", width=30),
                DataColumn(header="Version", width=9),
                DataColumn(header="Token", width=14),
                DataColumn(header="Connected", width=17),
            ],
            rows=rows,
        )
    )


@instance_app.command("status")
def instance_status(profile: str = typer.Argument("")) -> None:
    """Show metadata and snapshot summary for an instance."""
    registry, meta = _resolve_profile(profile)

    console.print()
    console.print(
        KeyValuePanel(
            title="Instance",
            rows=[
                KvRow(label="Instance", value=meta.profile),
                KvRow(label="URL", value=meta.url),
                KvRow(label="Version", value=meta.sn_version),
                KvRow(label="Token", value=token_badge(meta)),
                KvRow(
                    label="Connected",
                    value=meta.last_connected_at.strftime("%Y-%m-%d %H:%M UTC"),
                ),
            ],
        )
    )

    snapshot = registry.load_snapshot(meta.profile)
    if snapshot is None:
        console.print()
        console.print(
            Hint(label="No snapshot", command="nexus instance refresh", suffix="to capture one")
        )
        return

    c = snapshot.counts
    custom_flows = sum(1 for f in snapshot.flows if f.is_custom)
    custom_brs = sum(1 for r in snapshot.business_rules if r.is_custom)
    custom_sis = sum(1 for s in snapshot.script_includes if s.is_custom)
    console.print()
    console.print(
        KeyValuePanel(
            title="Snapshot",
            rows=[
                KvRow(
                    label="Captured",
                    value=snapshot.captured_at.strftime("%Y-%m-%d %H:%M UTC"),
                ),
                KvRow(label="AI Skills", value=str(c.ai_skills)),
                KvRow(label="Flows", value=f"{c.flows} ({custom_flows} custom)"),
                KvRow(
                    label="Business Rules",
                    value=f"{c.business_rules} ({custom_brs} custom)",
                ),
                KvRow(
                    label="Script Includes",
                    value=f"{c.script_includes} ({custom_sis} custom)",
                ),
            ],
        )
    )


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

    console.print(Notice.info(f"Deleted instance {profile!r}."))


@instance_app.command("use")
def instance_use(profile: str) -> None:
    """Set the default instance."""
    _resolve_profile(profile)
    _set_default_profile(NexusPaths.from_env(), profile)
    console.print(Notice.info(f"Default instance set to {profile!r}."))


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
            err_console.print(Notice.error(f"Probe failed: HTTP {resp.status_code}"))
            raise typer.Exit(1)
    except httpx.RequestError as exc:
        err_console.print(Notice.error(f"Cannot reach {meta.url}: {exc}"))
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
        Notice.info(
            f"Connected to {profile!r}. Token valid until {new_expiry.strftime('%H:%M UTC')}."
        )
    )


@instance_app.command("refresh")
def instance_refresh(profile: str = typer.Argument("")) -> None:
    """Pull a fresh artifact snapshot from the instance."""
    registry, meta, token, new_expiry = _acquire_token(profile)
    profile = meta.profile

    console.print(Notice.info(f"Capturing snapshot from {profile!r}..."))
    try:
        snapshot = asyncio.run(InstanceScanner().scan(meta.url, token, meta.sn_version))
    except SnapshotError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc

    registry.save_snapshot(profile, snapshot)
    c = snapshot.counts
    registry.save(meta.model_copy(update={"token_expires_at": new_expiry, "snapshot_counts": c}))
    console.print(
        Notice.info(
            f"Snapshot captured: {c.ai_skills} AI skills, {c.flows} flows, "
            f"{c.business_rules} business rules, {c.script_includes} script includes."
        )
    )


@instance_app.command("register")
def instance_register(profile: str) -> None:
    """Interactive wizard to register a new ServiceNow instance via OAuth2."""
    paths = NexusPaths.from_env()
    if (paths.instances_dir / profile).exists():
        err_console.print(
            Notice.error(
                f"Profile {profile!r} already exists. "
                f"Delete it first with 'nexus instance delete {profile}'."
            )
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
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc

    sn_version, sn_build, instance_name = _detect_sn_version(
        url, token_response.access_token, profile
    )
    if sn_version == "unknown":
        console.print(
            Notice.warn(
                "Version: unknown (glide.buildtag not in sys_properties -- "
                "run with --log-level DEBUG to diagnose)"
            )
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
    console.print(Notice.info(f"Registered {profile} ({sn_version})."))

    if not ConfigManager(paths).load().instances.default:
        _set_default_profile(paths, profile)
        console.print(Notice.info("Set as default instance."))


@capture_app.callback(invoke_without_command=True)
def capture_callback(ctx: typer.Context) -> None:
    """Show local archives and available commands."""
    if ctx.invoked_subcommand is not None:
        return
    capture_list()
    console.print(CommandGuide(app_name="nexus capture", items=_CAPTURE_HELP))


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

        with nexus_progress(console) as progress:
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
            console.print(Notice.info(f"No scopes with custom configurations found on {resolved}."))
            return

        all_s = list(manifest.scopes)
        custom_s = [s for s in all_s if s.scope.startswith(_CUSTOM_SCOPE_PREFIXES)]

        def _total(s: ScopeEntry) -> int:
            return sum(s.table_counts.values())

        custom_s.sort(key=_total, reverse=True)
        display = all_s if all_scopes else (custom_s if custom_s else all_s)

        group_obj = DEFAULT_TABLE_GROUPS.get(group)
        columns: list[DataColumn] = [
            DataColumn(header="Scope Key", width=_SCOPE_KEY_WIDTH),
            DataColumn(header="Name", width=_SCOPE_NAME_WIDTH),
        ]
        if group_obj:
            for spec in group_obj.tables:
                hdr = _TABLE_HEADER.get(spec.name, spec.display[:4])
                columns.append(DataColumn(header=hdr, width=5, justify="right"))

        rows: list[list[RenderableType]] = []
        for scope in display:
            row: list[RenderableType] = [
                _trunc(scope.scope, _SCOPE_KEY_WIDTH),
                _trunc(scope.name, _SCOPE_NAME_WIDTH),
            ]
            if group_obj:
                for spec in group_obj.tables:
                    row.append(str(scope.table_counts.get(spec.name, 0)))
            rows.append(row)

        console.print(DataTable(title=f"Custom scopes on {resolved}", columns=columns, rows=rows))

        if all_scopes or not custom_s:
            summary = f"{len(display)} scopes with custom configs on {resolved}"
        else:
            summary = (
                f"Showing {len(custom_s)} of your custom scopes "
                f"({len(all_s)} total with configs). Use --all to show all."
            )
        console.print(Notice.info(summary))

        if display:
            example = display[0].scope
            console.print()
            console.print(Hint(label="Next", command=f"nexus capture pull --scope {example}"))
            if len(display) > 1:
                console.print(
                    Hint(
                        label="Tip",
                        command="--scope x_a --scope x_b",
                        suffix="captures multiple at once",
                    )
                )

    asyncio.run(_run())


_UUID_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


async def _resolve_scope_ids(
    scope_args: list[str],
    client: ServiceNowClient,
) -> list[str]:
    """Resolve scope keys (x_snc_*) or sys_ids to sys_ids.

    UUID args are passed through unchanged. Scope keys are resolved with a
    single direct sys_scope lookup instead of a full grouped-count discover.

    Args:
        scope_args: List of scope keys or sys_ids from --scope options.
        client: Open ServiceNowClient to use for key lookups.

    Returns:
        List of resolved sys_ids in the same order as scope_args.
    """
    keys_to_lookup = [s for s in scope_args if not _UUID_RE.match(s.replace("-", ""))]

    if not keys_to_lookup:
        return scope_args

    # One direct query for all keys -- far cheaper than a full discover
    in_query = f"scopeIN{','.join(keys_to_lookup)}"
    async with client:
        rows = await client.list_records(
            "sys_scope",
            query=in_query,
            fields="sys_id,scope",
            limit=len(keys_to_lookup) + 1,
        )
    key_map = {str(r.get("scope", "")): str(r.get("sys_id", "")) for r in rows}

    resolved: list[str] = []
    for arg in scope_args:
        if _UUID_RE.match(arg.replace("-", "")):
            resolved.append(arg)
        elif arg in key_map:
            resolved.append(key_map[arg])
            console.print(Notice.info(f"Resolved {arg} -> {key_map[arg]}"))
        else:
            err_console.print(
                Notice.error(
                    f"Scope {arg!r} not found. "
                    f"Run 'nexus capture discover' to see available scopes."
                )
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

        # Resolve scope keys before opening the capture connection
        scope_ids = await _resolve_scope_ids(scope, client)

        with nexus_progress(console) as progress:
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
        console.print(
            KeyValuePanel(
                title="Capture complete",
                rows=[
                    KvRow(label="Records", value=f"{manifest.record_count:,}"),
                    KvRow(label="Archive", value=str(manifest.archive_dir)),
                    KvRow(
                        label="Next",
                        value=f"nexus capture push {manifest.archive_dir}",
                    ),
                ],
            )
        )

    asyncio.run(_run())


@capture_app.command("list")
def capture_list(
    instance: Annotated[str | None, typer.Argument(help="Filter by instance")] = None,
) -> None:
    """List local capture archives."""
    archives_root = NexusPaths.from_env().archives_dir
    if not archives_root.exists():
        console.print(
            Hint(label="No archives yet", command="nexus capture pull", suffix="to capture one")
        )
        return

    rows: list[list[RenderableType]] = []
    for manifest_path in sorted(archives_root.rglob("manifest.yaml")):
        try:
            raw = _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest = ArchiveManifest.model_validate(raw, strict=False)
        except Exception as exc:
            err_console.print(
                Notice.warn(f"Skipping corrupt manifest {manifest_path.parent}: {exc}")
            )
            continue
        if instance and manifest.instance_id != instance:
            continue
        rows.append(
            [
                manifest.instance_id,
                str(manifest.captured_at)[:19],
                str(manifest.record_count),
                _trunc(str(manifest.archive_dir), 45),
            ]
        )
    console.print(
        DataTable(
            title="Archives",
            columns=[
                DataColumn(header="Instance", width=12),
                DataColumn(header="Captured", width=20),
                DataColumn(header="Recs", width=6, justify="right"),
                DataColumn(header="Archive"),
            ],
            rows=rows,
        )
    )


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
            resolved_instance = instance or _config_default()
        ref = await engine.push_to_update_set(result, resolved_instance, update_set)
        console.print(
            KeyValuePanel(
                title="Push complete",
                rows=[
                    KvRow(label="Records", value=str(ref.record_count)),
                    KvRow(label="Update set", value=ref.name),
                    KvRow(label="sys_id", value=ref.sys_id),
                ],
            )
        )

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
def sync() -> None:
    """Pull the latest templates from the GitHub registry."""
    console.print(Notice.info("Syncing templates -- not yet implemented."))
    console.print(Notice.info("Configure github_repo in ~/.nexus/config.yaml first."))


@app.command("templates")
def templates_cmd() -> None:
    """Browse and inspect available templates."""
    console.print(Notice.info("Template browser -- not yet implemented. Run 'nexus sync' first."))


@app.command()
def assess(
    for_template: Annotated[
        str, typer.Option("--for", help="Check readiness for a specific template")
    ] = "",
    job: Annotated[str, typer.Option("--job", help="Validate a past deployment by job ID")] = "",
) -> None:
    """Run an instance health scan or targeted assessment."""
    if for_template:
        console.print(
            Notice.info(f"Readiness check for template: {for_template!r} -- not yet implemented.")
        )
    elif job:
        console.print(
            Notice.info(f"Post-deploy validation for job: {job!r} -- not yet implemented.")
        )
    else:
        console.print(Notice.info("Instance health scan -- not yet implemented."))


@app.command()
def apply(
    template: Annotated[str, typer.Argument(help="Template name to deploy")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Deploy a template to the configured ServiceNow instance."""
    console.print(
        Notice.info(f"Applying template: {template!r} (dry_run={dry_run}) -- not yet implemented.")
    )


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


if __name__ == "__main__":
    app()
