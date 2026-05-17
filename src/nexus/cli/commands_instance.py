# src/nexus/cli/commands_instance.py
# 'nexus instance' command implementations extracted for ADR-023 sizing.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Typer commands under the instance sub-app.

Extracted from cli/__init__.py to keep that module marching toward
the 800-line cap defined by ADR-023. Each function here is decorated
with @instance_app.command(...) (or the sub-app callback) so the
mere act of importing this module registers every command with the
shared :data:.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated

import httpx
import typer
from rich.console import RenderableType
from rich.text import Text

from nexus.cli.apps import instance_app
from nexus.cli.auth import (
    acquire_token as _acquire_token,
)
from nexus.cli.auth import (
    config_default as _config_default,
)
from nexus.cli.auth import (
    detect_sn_version as _detect_sn_version,
)
from nexus.cli.auth import (
    instance_registry as _instance_registry,
)
from nexus.cli.auth import (
    oauth_for as _oauth_for,
)
from nexus.cli.auth import (
    resolve_profile as _resolve_profile,
)
from nexus.cli.auth import (
    set_default_profile as _set_default_profile,
)
from nexus.cli.console import console, err_console
from nexus.cli.help_text import (
    INSTANCE_HELP,
    INSTANCE_PARENT,
    guide_items,
)
from nexus.cli.oauth import provision_oauth
from nexus.cli.utils import trunc as _trunc
from nexus.config.manager import ConfigManager
from nexus.config.paths import NexusPaths
from nexus.config.settings import InstancesConfig
from nexus.instances.badges import token_badge
from nexus.instances.errors import OAuthError, SnapshotError
from nexus.instances.models import InstanceMeta, InstanceSnapshot
from nexus.instances.oauth import SNOAuthClient
from nexus.instances.registry import InstanceRegistry
from nexus.instances.scanner import InstanceScanner
from nexus.plugins import PluginInventory, PluginScanError, PluginScanner
from nexus.ui import (
    CommandGuide,
    CommandHelp,
    DataColumn,
    DataTable,
    Hint,
    KeyValuePanel,
    KvRow,
    Notice,
    default_marker,
)

__all__: list[str] = []


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

    console.print(CommandHelp(title="nexus instance", entry=INSTANCE_PARENT))
    console.print(CommandGuide(app_name="nexus instance", items=guide_items(INSTANCE_HELP)))


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
    profile: Annotated[str, typer.Argument(help="Instance profile to delete")],
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
        remaining = registry.list_all()
        if len(remaining) == 1:
            # Exactly one instance left -- promote it automatically so the
            # user never has to think about a default again.
            survivor = remaining[0].profile
            _set_default_profile(paths, survivor)
            console.print(Notice.info(f"Default instance promoted to {survivor!r}."))
        else:
            manager.save(cfg.model_copy(update={"instances": InstancesConfig(default="")}))
            if remaining:
                console.print(
                    Notice.warn(
                        f"Default instance cleared. {len(remaining)} instances remain -- "
                        f"pick one with 'nexus instance use <profile>'."
                    )
                )

    console.print(Notice.info(f"Deleted instance {profile!r}."))


@instance_app.command("use")
def instance_use(
    profile: Annotated[str, typer.Argument(help="Instance profile to set as default")] = "",
) -> None:
    """Set the default instance (interactive picker when invoked with no profile)."""
    if not profile:
        registered = _instance_registry().list_all()
        if not registered:
            err_console.print(Notice.error("No instances registered."))
            console.print(Hint(label="Register one", command="nexus instance register dev"))
            raise typer.Exit(1)
        if len(registered) == 1:
            profile = registered[0].profile
            console.print(
                Notice.info(f"Only one instance registered; setting {profile!r} as default.")
            )
        else:
            current_default = _config_default()
            console.print(Notice.info("Multiple instances registered. Pick a default:"))
            for i, meta in enumerate(registered, start=1):
                marker = "*" if meta.profile == current_default else " "
                console.print(f"  {marker} {i}. {meta.profile}  ({meta.url})")
            try:
                raw_choice: object = typer.prompt("Enter number", type=int)
            except typer.Abort:
                raise typer.Exit(1) from None
            choice = int(raw_choice) if isinstance(raw_choice, int | str) else 0
            if choice < 1 or choice > len(registered):
                err_console.print(Notice.error(f"Invalid choice: {choice}"))
                raise typer.Exit(1)
            profile = registered[choice - 1].profile
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
def instance_refresh(
    profile: str = typer.Argument(""),
    no_counts: Annotated[
        bool,
        typer.Option(
            "--no-counts",
            help="Skip per-plugin record-count capture for a faster refresh.",
        ),
    ] = False,
) -> None:
    """Pull a fresh artifact snapshot from the instance."""
    registry, meta, token, new_expiry = _acquire_token(profile)
    profile = meta.profile

    console.print(Notice.info(f"Capturing snapshot from {profile!r}..."))

    async def _run() -> tuple[InstanceSnapshot, PluginInventory | None]:
        scanner = InstanceScanner()
        plugin_scanner = PluginScanner()
        snapshot_task = scanner.scan(meta.url, token, meta.sn_version)
        plugin_task = plugin_scanner.scan(
            meta.url, token, meta.sn_version, capture_counts=not no_counts
        )
        results = await asyncio.gather(snapshot_task, plugin_task, return_exceptions=True)
        snap_result, plugin_result = results
        if isinstance(snap_result, BaseException):
            raise snap_result
        if isinstance(plugin_result, PluginScanError):
            err_console.print(Notice.warn(f"Plugin scan failed: {plugin_result}"))
            return snap_result, None
        if isinstance(plugin_result, BaseException):
            raise plugin_result
        return snap_result, plugin_result

    try:
        snapshot, plugin_inventory = asyncio.run(_run())
    except SnapshotError as exc:
        err_console.print(Notice.error(str(exc)))
        raise typer.Exit(1) from exc

    registry.save_snapshot(profile, snapshot)
    if plugin_inventory is not None:
        registry.save_plugin_inventory(profile, plugin_inventory)
    c = snapshot.counts
    plugin_count = len(plugin_inventory.plugins) if plugin_inventory else 0
    counts = c.model_copy(update={"plugins": plugin_count})
    registry.save(
        meta.model_copy(update={"token_expires_at": new_expiry, "snapshot_counts": counts})
    )
    console.print(
        Notice.info(
            f"Snapshot captured: {c.ai_skills} AI skills, {c.flows} flows, "
            f"{c.business_rules} business rules, {c.script_includes} script includes."
        )
    )


@instance_app.command("register")
def instance_register(
    profile: Annotated[str, typer.Argument(help="Profile name to register")],
) -> None:
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

    client_id, client_secret = provision_oauth(url, profile, username, password)

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
