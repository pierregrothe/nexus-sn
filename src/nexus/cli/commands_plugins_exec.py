# src/nexus/cli/commands_plugins_exec.py
# Typer commands for destructive plugin ops (install/activate/upgrade/apply/etc).
# Author: Pierre Grothe
# Date: 2026-05-16
"""`nexus plugins` destructive commands.

Extracted from ``cli/__init__.py`` per ADR-023. Every command here hits
the ServiceNow API and changes instance state.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast

import typer
import yaml as _yaml

from nexus.cli.apps import plugins_app
from nexus.cli.auth import acquire_token as _acquire_token
from nexus.cli.console import console, err_console
from nexus.cli.renderables import (
    cascade_actionable,
    cascade_scope,
    cascade_summary_notice,
    dependencies_panel,
    result_panel,
)
from nexus.cli.views import (
    _load_inventory_or_exit,
    _plugins_for,
    _rescan_plugin_inventory,
    _validate_family_filter,
)
from nexus.connectors.servicenow.client import RefreshTokenCallback, ServiceNowClient
from nexus.plugins.diff import PromotionPlan
from nexus.plugins.models import PluginInfo
from nexus.plugins.updates import plugins_with_updates
from nexus.ui import Hint, Notice, nexus_progress

if TYPE_CHECKING:
    from datetime import datetime

    from nexus.plugins.progress import ProgressState


__all__: list[str] = []


def _build_refresh_callback(profile: str) -> RefreshTokenCallback:
    """Build a RefreshTokenCallback that re-acquires the token for ``profile``.

    The returned coroutine wraps :func:`nexus.cli.auth.acquire_token` so
    :class:`ServiceNowClient` can transparently refresh during long-running
    operations (batch upgrades that outlive their initial OAuth grant).

    Args:
        profile: Instance profile name to re-resolve tokens for.

    Returns:
        Async callable returning ``(token, expires_at)``.
    """

    async def _refresh() -> tuple[str, datetime]:
        _registry, _meta, new_token, new_expiry = _acquire_token(profile)
        return new_token, new_expiry

    return _refresh


@plugins_app.command("install")
def plugins_install(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to install (e.g. com.snc.discovery)")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    version: Annotated[
        str | None, typer.Option("--version", help="Pin to this version (default: latest)")
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
) -> None:
    """Install a plugin on the resolved instance.

    Shows the SN dependency cascade pre-flight, prompts for confirmation
    (unless ``--yes``), then blocks with a progress bar until SN reports
    terminal status.
    """
    from nexus.plugins.dependencies import fetch_dependencies  # noqa: PLC0415
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            deps = await fetch_dependencies(client, plugin_id, version)
            if deps:
                console.print(dependencies_panel(deps, plugin_id))
            if not yes and not typer.confirm(f"Install {plugin_id} against {meta.profile}?"):
                raise typer.Exit(0)
            executor = PluginExecutor(client=client, inventory=inventory)
            result = await executor.install(plugin_id, version)
            console.print(result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())


@plugins_app.command("activate")
def plugins_activate(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to activate")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
) -> None:
    """Activate an installed plugin on the resolved instance."""
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            if not yes and not typer.confirm(f"Activate {plugin_id} against {meta.profile}?"):
                raise typer.Exit(0)
            executor = PluginExecutor(client=client, inventory=inventory)
            result = await executor.activate(plugin_id)
            console.print(result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())


@plugins_app.command("upgrade")
def plugins_upgrade(
    plugin_id: Annotated[
        str,
        typer.Argument(help="Plugin ID to upgrade. Omit to upgrade every pending plugin."),
    ] = "",
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    family: Annotated[
        list[str] | None,
        typer.Option(
            "--family",
            help="Batch-upgrade pending plugins matching one or more families "
            "(case-insensitive, repeatable). Mutually exclusive with PLUGIN_ID and --all.",
        ),
    ] = None,
    all_pending: Annotated[
        bool,
        typer.Option(
            "--all",
            help="Batch-upgrade every pending plugin on the instance. "
            "Same as bare `upgrade`; the explicit form is preferred in scripts.",
        ),
    ] = False,
    to: Annotated[
        str | None,
        typer.Option(
            "--to", help="Target version (single-plugin mode only; default: latest available)"
        ),
    ] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
    out: Annotated[
        str,
        typer.Option(
            "--out",
            help="Batch mode: write BatchUpgradeReport YAML to this path after the run.",
        ),
    ] = "",
) -> None:
    """Upgrade plugin(s) on the resolved instance.

    Four invocations:

    * ``nexus plugins upgrade <id>`` -- upgrade one plugin (with cascade).
    * ``nexus plugins upgrade --family X`` -- batch-upgrade pending plugins
      in one or more families.
    * ``nexus plugins upgrade --all`` -- batch-upgrade every pending plugin.
    * ``nexus plugins upgrade`` -- bare form; same as ``--all``.

    ``--to`` only applies to single-plugin mode. ``--out`` only applies to
    batch mode. List pending updates first with ``nexus plugins outdated``.
    """
    if plugin_id and family:
        err_console.print(Notice.error("--family cannot be combined with a positional PLUGIN_ID."))
        raise typer.Exit(2)
    if plugin_id and all_pending:
        err_console.print(Notice.error("--all cannot be combined with a positional PLUGIN_ID."))
        raise typer.Exit(2)
    if all_pending and family:
        err_console.print(Notice.error("--all cannot be combined with --family."))
        raise typer.Exit(2)
    if to is not None and not plugin_id:
        err_console.print(Notice.error("--to requires a positional PLUGIN_ID."))
        raise typer.Exit(2)
    if out and plugin_id:
        err_console.print(
            Notice.error(
                "--out only applies to batch mode (omit PLUGIN_ID, use --family or --all)."
            )
        )
        raise typer.Exit(2)
    if plugin_id:
        _upgrade_single(plugin_id, instance, to, yes)
    else:
        _upgrade_batch(instance, tuple(family) if family else (), yes, out)


def _upgrade_single(plugin_id: str, instance: str, to: str | None, yes: bool) -> None:
    """Single-plugin upgrade with cascade preview and Stage K/N progress."""
    from nexus.plugins.dependencies import fetch_dependencies  # noqa: PLC0415
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    registry, _, token, expiry = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(
            instance_url=meta.url,
            token=token,
            refresh_token_callback=_build_refresh_callback(meta.profile),
            token_expires_at=expiry,
        ) as client:
            deps = await fetch_dependencies(client, plugin_id, to)
            actionable = cascade_actionable(deps)
            if deps:
                console.print(dependencies_panel(deps, plugin_id))
            if actionable:
                console.print(cascade_summary_notice(actionable, plugin_id))
            if not yes and not typer.confirm(f"Upgrade {plugin_id} on {meta.profile}?"):
                raise typer.Exit(0)
            executor = PluginExecutor(client=client, inventory=inventory)
            cascade_scopes: tuple[str, ...] = (
                *(cascade_scope(d) for d in actionable),
                plugin_id,
            )
            total_stages = len(cascade_scopes)
            seen_stages: set[str] = set()
            with nexus_progress(console) as progress:
                task = progress.add_task(f"Upgrading {plugin_id}", total=100)

                def on_progress(state: ProgressState) -> None:
                    label = state.status_label or f"Upgrading {plugin_id}"
                    label_lc = label.lower()
                    for scope in cascade_scopes:
                        if scope and scope.lower() in label_lc:
                            seen_stages.add(scope)
                    if total_stages > 1 and seen_stages:
                        k = min(len(seen_stages), total_stages)
                        label = f"Stage {k}/{total_stages}: {label}"
                    progress.update(task, completed=state.percent_complete, description=label)

                result = await executor.upgrade(plugin_id, to, on_progress=on_progress)
            console.print(result_panel(result))
            if not result.success:
                raise typer.Exit(1)
        await _rescan_plugin_inventory(meta, token, registry)

    asyncio.run(_run())


def _upgrade_batch(
    instance: str,
    families: tuple[str, ...],
    yes: bool,
    out: str,
) -> None:
    """Batch upgrade every pending plugin, optionally filtered by family."""
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    meta, inventory = _load_inventory_or_exit(instance)
    pending = plugins_with_updates(inventory)
    if families:
        from nexus.plugins.filters import filter_by_family  # noqa: PLC0415

        _validate_family_filter(inventory, families)
        pending = filter_by_family(pending, families)

    if not pending:
        console.print(Notice.info("Nothing to upgrade."))
        return
    if not yes and not typer.confirm(f"Upgrade {len(pending)} plugin(s) on {meta.profile}?"):
        raise typer.Exit(0)

    registry, _, token, expiry = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(
            instance_url=meta.url,
            token=token,
            refresh_token_callback=_build_refresh_callback(meta.profile),
            token_expires_at=expiry,
        ) as client:
            executor = PluginExecutor(client=client, inventory=inventory)
            with nexus_progress(console) as progress:
                batch_task = progress.add_task("Batch upgrade", total=len(pending))
                plugin_task = progress.add_task("Waiting...", total=100, visible=False)
                current_label: dict[str, str] = {"text": "Waiting..."}

                def on_plugin_start(_index: int, p: PluginInfo) -> None:
                    current_label["text"] = f"Upgrading {p.plugin_id}"
                    progress.reset(plugin_task)
                    progress.update(
                        plugin_task,
                        description=current_label["text"],
                        completed=0,
                        visible=True,
                    )

                def on_plugin_progress(state: ProgressState) -> None:
                    label = state.status_label or current_label["text"]
                    current_label["text"] = label
                    progress.update(
                        plugin_task,
                        completed=state.percent_complete,
                        description=label,
                    )

                def on_plugin_complete(_index: int, _result: object) -> None:
                    progress.update(batch_task, advance=1)
                    progress.update(plugin_task, visible=False)

                report = await executor.batch_upgrade(
                    pending,
                    families=families,
                    console=console,
                    on_plugin_start=on_plugin_start,
                    on_plugin_progress=on_plugin_progress,
                    on_plugin_complete=on_plugin_complete,
                )
            console.print(
                Notice.info(
                    f"{report.succeeded} upgraded, {report.failed} failed "
                    f"(of {report.target_count})."
                )
            )
            if out:
                Path(out).write_text(
                    _yaml.safe_dump(report.model_dump(), sort_keys=False),
                    encoding="utf-8",
                )
            if report.succeeded > 0:
                await _rescan_plugin_inventory(meta, token, registry)
            if report.exit_code != 0:
                raise typer.Exit(report.exit_code)

    asyncio.run(_run())


@plugins_app.command("apply")
def plugins_apply(
    plan_file: Annotated[Path, typer.Argument(help="Path to PromotionPlan YAML")],
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Override the plan's target_profile (default: use plan's target_profile)",
        ),
    ] = "",
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt")] = False,
) -> None:
    """Execute a PromotionPlan YAML produced by `nexus plugins promote`.

    Defaults the target instance to the plan's ``target_profile`` field so a
    dev->prod plan applies to prod even when the local default is dev. Use
    ``--instance`` to force a different target.

    Rolls back partial failures in reverse order (best-effort).
    """
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    if not plan_file.exists():
        err_console.print(Notice.error(f"Plan file not found: {plan_file}"))
        raise typer.Exit(2)
    raw_payload = _yaml.safe_load(plan_file.read_text(encoding="utf-8"))
    if isinstance(raw_payload, dict):
        payload = cast(dict[str, object], raw_payload)
        actions = payload.get("actions")
        if isinstance(actions, dict):
            flat: list[dict[str, object]] = []
            buckets = cast(dict[str, list[dict[str, object]]], actions)
            for action_name in ("install", "activate", "upgrade"):
                for row in buckets.get(action_name, []):
                    flat.append({"action": action_name, "current_version": None, **row})
            payload["actions"] = tuple(flat)
        elif isinstance(actions, list):
            payload["actions"] = tuple(cast(list[object], actions))
        plan = PromotionPlan.model_validate(payload)
    else:
        plan = PromotionPlan.model_validate(raw_payload)

    effective_instance = instance or plan.target_profile
    resolved = _plugins_for(effective_instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    registry, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            console.print(f"Plan: {len(plan.actions)} actions against {meta.profile}")
            if not yes and not typer.confirm("Proceed?"):
                raise typer.Exit(0)
            executor = PluginExecutor(client=client, inventory=inventory)
            log = await executor.apply_plan(plan, console=console)
            console.print(f"Done: {log.success_count} ok, {log.failure_count} failed")
            if log.failure_count:
                raise typer.Exit(1)
        await _rescan_plugin_inventory(meta, token, registry)

    asyncio.run(_run())


@plugins_app.command("deactivate")
def plugins_deactivate(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to deactivate")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Bypass the impact gate (requires typing the plugin id at the second prompt)",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the action confirmation prompt")] = False,
) -> None:
    """Deactivate a plugin on the resolved instance.

    The impact gate blocks the operation when the plugin has reverse-deps
    or SN reports dependents. ``--force`` bypasses the gate but always
    requires typing the plugin id at a second confirmation prompt;
    ``--yes`` only skips the first prompt and never the second.
    """
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            if not yes and not typer.confirm(f"Deactivate {plugin_id} on {meta.profile}?"):
                raise typer.Exit(0)
            if force:
                typed = typer.prompt(
                    f"--force bypasses the impact gate. Type the plugin id "
                    f"({plugin_id}) to confirm"
                )
                if typed != plugin_id:
                    err_console.print(Notice.error("Confirmation mismatch; aborting."))
                    raise typer.Exit(2)
            executor = PluginExecutor(client=client, inventory=inventory)
            result = await executor.deactivate(plugin_id, force=force)
            console.print(result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())


@plugins_app.command("uninstall")
def plugins_uninstall(
    plugin_id: Annotated[str, typer.Argument(help="Plugin ID to uninstall")],
    instance: Annotated[
        str, typer.Option("--instance", help="Instance profile (default: configured default)")
    ] = "",
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Bypass the impact gate (requires typing the plugin id at the second prompt)",
        ),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the action confirmation prompt")] = False,
) -> None:
    """Uninstall a non-base plugin on the resolved instance.

    Base ServiceNow plugins (source == 'servicenow') cannot be uninstalled
    via REST and are refused unconditionally -- ``--force`` does NOT bypass
    that refusal. For non-base plugins the impact gate applies the same way
    as ``deactivate``: it blocks on non-zero reverse-deps unless ``--force``
    is given with a type-the-plugin-id confirmation.
    """
    from nexus.plugins.executor import PluginExecutor  # noqa: PLC0415

    resolved = _plugins_for(instance)
    if resolved is None:
        console.print(Notice.warn("Plugin inventory empty."))
        console.print(Hint(label="Refresh", command="nexus instance refresh"))
        raise typer.Exit(1)
    meta, inventory = resolved
    _, _, token, _ = _acquire_token(meta.profile)

    async def _run() -> None:
        async with ServiceNowClient(instance_url=meta.url, token=token) as client:
            if not yes and not typer.confirm(f"Uninstall {plugin_id} on {meta.profile}?"):
                raise typer.Exit(0)
            if force:
                typed = typer.prompt(
                    f"--force bypasses the impact gate. Type the plugin id "
                    f"({plugin_id}) to confirm"
                )
                if typed != plugin_id:
                    err_console.print(Notice.error("Confirmation mismatch; aborting."))
                    raise typer.Exit(2)
            executor = PluginExecutor(client=client, inventory=inventory)
            result = await executor.uninstall(plugin_id, force=force)
            console.print(result_panel(result))
            if not result.success:
                raise typer.Exit(1)

    asyncio.run(_run())
