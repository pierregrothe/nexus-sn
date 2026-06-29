# src/nexus/cli/commands_assess_replatform.py
# `nexus assess inventory` + `nexus assess migration` subcommands.
# Author: Pierre Grothe
# Date: 2026-06-29

"""Replatform subcommands under the assess group.

``inventory`` classifies one instance into a use-case inventory; ``migration``
diffs two instances into a bi-directional checklist. The Typer command bodies are
thin wrappers over ``run_inventory`` / ``run_migration``, which take an injectable
``ReplatformCollaborators`` so tests drive them with a fake inventory builder --
no ctx.obj, which would clash with the RenderContext set by the root callback.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated

import typer

from nexus.capture.engine import CaptureEngine
from nexus.capture.models import CaptureResult, ScopeManifest
from nexus.capture.scope import ScopeDiscoverer
from nexus.capture.tables import AI_AUTOMATION, DEFAULT_TABLE_GROUPS
from nexus.cli.apps import assess_app
from nexus.cli.auth import acquire_token as _acquire_token
from nexus.cli.console import console
from nexus.cli.console import render_context as _render_context
from nexus.config.paths import NexusPaths
from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.replatform.classifier import classify
from nexus.replatform.diff import build_checklist
from nexus.replatform.models import UseCaseInventory
from nexus.replatform.reporter import render_checklist, write_markdown
from nexus.schema.product_registry import ProductRegistry
from nexus.ui import nexus_progress
from nexus.ui.render_context import RenderContext

__all__ = [
    "ReplatformCollaborators",
    "default_replatform_collaborators",
    "parse_scope_aliases",
    "run_inventory",
    "run_migration",
]

# Scope-key prefixes that mark a user-developed (custom) scoped app.
_CUSTOM_PREFIXES = ("x_", "u_")


@dataclass(frozen=True, slots=True)
class ReplatformCollaborators:
    """Injectable seam for the replatform subcommands.

    Attributes:
        build_inventory: Given a profile name, return its UseCaseInventory.
            Production wires live capture + classify; tests inject a fake.
    """

    build_inventory: Callable[[str], UseCaseInventory]


def parse_scope_aliases(raw: list[str]) -> tuple[tuple[str, str], ...]:
    """Parse ``OLD=NEW`` ``--scope-alias`` values into ordered pairs.

    Args:
        raw: Raw ``OLD=NEW`` strings from the CLI.

    Returns:
        A tuple of ``(old, new)`` pairs.

    Raises:
        typer.BadParameter: When a value lacks ``=``.
    """
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if "=" not in item:
            raise typer.BadParameter(f"--scope-alias must be OLD=NEW, got {item!r}")
        old, new = item.split("=", 1)
        pairs.append((old, new))
    return tuple(pairs)


def run_inventory(
    *,
    profile: str,
    out: Path | None,
    render_context: RenderContext,
    collaborators: ReplatformCollaborators,
) -> int:
    """Build and render the use-case inventory for one instance.

    Args:
        profile: Instance profile to inventory.
        out: Optional path to write the inventory as JSON.
        render_context: Destination console + profile.
        collaborators: Injectable inventory builder.

    Returns:
        Exit code 0 on success.
    """
    inventory = collaborators.build_inventory(profile)
    coverage = ", ".join(inventory.coverage) or "-"
    render_context.console.print(
        f"inventory {profile}: {len(inventory.use_cases)} use case(s) coverage={coverage}",
        highlight=False,
    )
    for use_case in inventory.use_cases:
        render_context.console.print(
            f"  {use_case.domain}: {len(use_case.workflows)} workflow(s)", highlight=False
        )
    if out is not None:
        out.write_bytes(inventory.model_dump_json(indent=2).encode("utf-8"))
    return 0


def run_migration(
    *,
    from_profile: str,
    to_profile: str,
    aliases: tuple[tuple[str, str], ...],
    out: Path | None,
    render_context: RenderContext,
    collaborators: ReplatformCollaborators,
) -> int:
    """Diff two instances and render the replatform checklist.

    Args:
        from_profile: OLD instance profile (the source).
        to_profile: NEW instance profile (the target).
        aliases: ``(old, new)`` scope-rename pairs for matching.
        out: Optional path to write the checklist markdown.
        render_context: Destination console + profile.
        collaborators: Injectable inventory builder.

    Returns:
        Exit code 0 on success.
    """
    source = collaborators.build_inventory(from_profile)
    target = collaborators.build_inventory(to_profile)
    checklist = build_checklist(source, target, aliases)
    render_checklist(checklist, render_context)
    if out is not None:
        write_markdown(checklist, out)
    return 0


def default_replatform_collaborators(  # pragma: no cover -- production wiring
    paths: NexusPaths,
) -> ReplatformCollaborators:
    """Production wire-up: build inventories from live capture + the catalog."""

    def build(profile: str) -> UseCaseInventory:
        return _build_live_inventory(profile, paths)

    return ReplatformCollaborators(build_inventory=build)


def _build_live_inventory(  # pragma: no cover -- live I/O, exercised by smoke
    profile: str, paths: NexusPaths
) -> UseCaseInventory:
    """Discover + capture the instance live, then classify it."""
    manifest, capture = asyncio.run(_capture_live(profile))
    catalog = ProductRegistry(paths.schema_dir).load_catalog()
    return classify((capture,), manifest, catalog, profile=profile)


async def _capture_live(  # pragma: no cover -- live I/O, exercised by smoke
    profile: str,
) -> tuple[ScopeManifest, CaptureResult]:
    """Run live scope discovery + config capture for the AI_AUTOMATION group.

    Builds the client with a token refresh callback so the (often multi-minute)
    capture survives ServiceNow's ~30-minute OAuth token cap -- mirroring the
    plugin-executor long-operation pattern. Without it, a full capture dies with
    HTTP 401 mid-run.
    """
    _registry, meta, token, _expiry = _acquire_token(profile)

    async def _refresh() -> tuple[str, datetime]:
        _r, _m, new_token, new_expiry = _acquire_token(profile)
        return new_token, new_expiry

    async with ServiceNowClient(
        instance_url=meta.url, token=token, refresh_token_callback=_refresh
    ) as client:
        engine = CaptureEngine(client=client, archive_root=NexusPaths.from_env().archives_dir)
        discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
        with nexus_progress(console) as progress:
            task = progress.add_task("Discovering scopes...", total=None)

            def on_progress(completed: int, total: int, message: str) -> None:
                progress.update(
                    task,
                    description=message,
                    total=total if total > 0 else None,
                    completed=completed,
                )

            manifest = await discoverer.discover(
                profile, AI_AUTOMATION.key, on_progress=on_progress
            )
            # A replatform checklist cares about CUSTOM scoped apps (the use cases
            # built on the old instance), not the hundreds of out-of-box scopes --
            # capturing every OOB scope is both meaningless here and prohibitively slow.
            scope_ids = [
                entry.sys_id
                for entry in manifest.scopes
                if entry.scope.startswith(_CUSTOM_PREFIXES)
            ]
            capture = await engine.capture(
                profile, scope_ids, AI_AUTOMATION.key, on_progress=on_progress
            )
    return manifest, capture


@assess_app.command("inventory")
def assess_inventory(  # pragma: no cover -- thin Typer wrapper over run_inventory
    profile: Annotated[str, typer.Argument(help="Instance profile to inventory")],
    out: Annotated[
        str, typer.Option("--out", help="Write the inventory as JSON to this path")
    ] = "",
) -> None:
    """Classify one instance's captured config into a use-case inventory."""
    paths = NexusPaths.from_env()
    code = run_inventory(
        profile=profile,
        out=Path(out) if out else None,
        render_context=_render_context,
        collaborators=default_replatform_collaborators(paths),
    )
    raise typer.Exit(code)


@assess_app.command("migration")
def assess_migration(  # pragma: no cover -- thin Typer wrapper over run_migration
    from_profile: Annotated[str, typer.Option("--from", help="OLD instance profile")],
    to_profile: Annotated[str, typer.Option("--to", help="NEW (clean) instance profile")],
    scope_alias: Annotated[
        list[str] | None,
        typer.Option("--scope-alias", help="Map a renamed scope: OLD=NEW (repeatable)"),
    ] = None,
    out: Annotated[
        str, typer.Option("--out", help="Write the checklist markdown to this path")
    ] = "",
) -> None:
    """Diff two instances into a bi-directional replatform checklist."""
    paths = NexusPaths.from_env()
    code = run_migration(
        from_profile=from_profile,
        to_profile=to_profile,
        aliases=parse_scope_aliases(scope_alias or []),
        out=Path(out) if out else None,
        render_context=_render_context,
        collaborators=default_replatform_collaborators(paths),
    )
    raise typer.Exit(code)
