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
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, cast

import typer

from nexus.capture.models import CaptureResult, ConfigRecord, ScopeEntry, ScopeManifest
from nexus.capture.scope import ScopeDiscoverer
from nexus.capture.tables import DEFAULT_TABLE_GROUPS, TableGroup, TableSpec
from nexus.cli.apps import assess_app
from nexus.cli.auth import acquire_token as _acquire_token
from nexus.cli.console import console
from nexus.cli.console import render_context as _render_context
from nexus.config.paths import NexusPaths
from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.connectors.servicenow.errors import SNClientError
from nexus.replatform.classifier import classify
from nexus.replatform.diff import build_checklist
from nexus.replatform.domain_map import load_domain_map
from nexus.replatform.models import UseCaseInventory
from nexus.replatform.reporter import render_checklist, write_markdown
from nexus.schema.product_registry import ProductRegistry
from nexus.ui import nexus_progress
from nexus.ui.render_context import RenderContext

__all__ = [
    "ReplatformCollaborators",
    "default_replatform_collaborators",
    "parse_domain_map",
    "parse_scope_aliases",
    "resolve_groups",
    "run_inventory",
    "run_migration",
]

log = logging.getLogger(__name__)

# Scope-key prefixes that mark a user-developed (custom) scoped app.
_CUSTOM_PREFIXES = ("x_", "u_")
# Page size for listing artifacts per covered table.
_PAGE_SIZE = 1000


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


def parse_domain_map(raw: str) -> dict[str, str] | None:
    """Load ``--domain-map`` when given, translating errors to CLI errors.

    Args:
        raw: Path string from the CLI ("" when the option was omitted).

    Returns:
        The parsed overrides, or None when no map was supplied.

    Raises:
        typer.BadParameter: When the file is missing or malformed.
    """
    if not raw:
        return None
    try:
        return load_domain_map(Path(raw))
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc


def resolve_groups(raw: list[str]) -> tuple[TableGroup, ...]:
    """Resolve ``--group`` values against the registry; empty means all groups.

    Repeated keys are deduped, preserving first-occurrence order, so a
    duplicated ``--group`` never double-lists (and double-counts) a group.

    Args:
        raw: Group keys from the CLI.

    Returns:
        The selected TableGroups in registry order (or CLI order when given).

    Raises:
        typer.BadParameter: When a key is not a registered table group.
    """
    raw = list(dict.fromkeys(raw))
    if not raw:
        return tuple(DEFAULT_TABLE_GROUPS.values())
    unknown = [key for key in raw if key not in DEFAULT_TABLE_GROUPS]
    if unknown:
        raise typer.BadParameter(
            f"unknown table group(s): {', '.join(unknown)}; "
            f"valid: {', '.join(DEFAULT_TABLE_GROUPS)}"
        )
    return tuple(DEFAULT_TABLE_GROUPS[key] for key in raw)


def _merge_manifests(manifests: tuple[ScopeManifest, ...]) -> ScopeManifest:
    """Union per-group ScopeManifests by scope sys_id.

    Args:
        manifests: One manifest per discovered table group (at least one).

    Returns:
        A manifest whose scopes are the by-sys_id union, table counts merged,
        sorted by sys_id for stable output.

    Raises:
        ValueError: If ``manifests`` is empty.
    """
    if not manifests:
        raise ValueError("at least one manifest is required")
    by_id: dict[str, ScopeEntry] = {}
    for manifest in manifests:
        for entry in manifest.scopes:
            existing = by_id.get(entry.sys_id)
            if existing is None:
                by_id[entry.sys_id] = entry
            else:
                merged = dict(existing.table_counts) | dict(entry.table_counts)
                by_id[entry.sys_id] = existing.model_copy(update={"table_counts": merged})
    first = manifests[0]
    return ScopeManifest(
        instance_id=first.instance_id,
        captured_at=first.captured_at,
        scopes=tuple(sorted(by_id.values(), key=lambda entry: entry.sys_id)),
    )


def _warn_skipped_tables(
    render_context: RenderContext, profile: str, tables: tuple[str, ...], artifact: str
) -> None:
    """Print the absent-tables warning for one instance's inventory.

    Args:
        render_context: Destination console.
        profile: Instance profile the tables were absent on.
        tables: Sorted absent table names.
        artifact: What excludes them in the message ("inventory" or "checklist").
    """
    render_context.console.print(
        f"warning: tables absent on {profile}: {', '.join(tables)}" f" -- {artifact} excludes them",
        highlight=False,
    )


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
    if inventory.skipped_tables:
        _warn_skipped_tables(render_context, profile, inventory.skipped_tables, "inventory")
    if out is not None:
        out.write_bytes(inventory.model_dump_json(indent=2).encode("utf-8"))
    return 0


def run_migration(
    *,
    from_profile: str,
    to_profile: str,
    aliases: tuple[tuple[str, str], ...],
    out: Path | None,
    out_json: Path | None,
    render_context: RenderContext,
    collaborators: ReplatformCollaborators,
) -> int:
    """Diff two instances and render the replatform checklist.

    Args:
        from_profile: OLD instance profile (the source).
        to_profile: NEW instance profile (the target).
        aliases: ``(old, new)`` scope-rename pairs for matching.
        out: Optional path to write the checklist markdown.
        out_json: Optional path to write the checklist as MigrationChecklist
            JSON, the shape ``nexus migrate select --from-checklist`` consumes.
        render_context: Destination console + profile.
        collaborators: Injectable inventory builder.

    Returns:
        Exit code 0 on success.
    """
    source = collaborators.build_inventory(from_profile)
    target = collaborators.build_inventory(to_profile)
    for inventory in (source, target):
        if inventory.skipped_tables:
            _warn_skipped_tables(
                render_context, inventory.profile, inventory.skipped_tables, "checklist"
            )
    checklist = build_checklist(source, target, aliases)
    render_checklist(checklist, render_context)
    if out is not None:
        write_markdown(checklist, out)
    if out_json is not None:
        out_json.write_bytes(checklist.model_dump_json(indent=2).encode("utf-8"))
    return 0


def default_replatform_collaborators(  # pragma: no cover -- production wiring
    paths: NexusPaths,
    *,
    groups: tuple[TableGroup, ...],
    overrides: dict[str, str] | None = None,
) -> ReplatformCollaborators:
    """Production wire-up: build inventories from live capture + the catalog.

    Args:
        paths: Resolved NEXUS paths (schema catalog directory).
        groups: Table groups to cover when listing artifacts.
        overrides: Optional scope-key -> business-domain overrides for
            classification.

    Returns:
        A ReplatformCollaborators whose build_inventory lists live artifacts
        and classifies them for the given profile.
    """

    def build(profile: str) -> UseCaseInventory:
        return _build_live_inventory(profile, paths, groups=groups, overrides=overrides)

    return ReplatformCollaborators(build_inventory=build)


def _build_live_inventory(  # pragma: no cover -- live I/O, exercised by smoke
    profile: str,
    paths: NexusPaths,
    *,
    groups: tuple[TableGroup, ...],
    overrides: dict[str, str] | None = None,
) -> UseCaseInventory:
    """List the instance's custom artifacts live across table groups, then classify.

    Args:
        profile: Instance profile to inventory.
        paths: Resolved NEXUS paths (schema catalog directory).
        groups: Table groups to cover when listing artifacts.
        overrides: Optional scope-key -> business-domain overrides for
            classification.

    Returns:
        The classified UseCaseInventory for this profile.
    """
    manifest, captures, skipped = asyncio.run(_list_artifacts_live(profile, groups))
    catalog = ProductRegistry(paths.schema_dir).load_catalog()
    return classify(
        captures,
        manifest,
        catalog,
        profile=profile,
        skipped_tables=skipped,
        overrides=overrides,
    )


def _scope_query(spec: TableSpec, scope_csv: str, *, customer_only: bool) -> str:
    """Build the per-table listing query for a set of scope sys_ids.

    Args:
        spec: Table being listed.
        scope_csv: Comma-joined scope sys_ids.
        customer_only: Restrict to customer-created/modified records -- used
            for the global scope, where OOB records vastly outnumber custom.

    Returns:
        An encoded sysparm query string.
    """
    query = f"{spec.scope_field}IN{scope_csv}"
    if customer_only:
        query += "^sys_customer_update=true"
    return query


async def _list_artifacts_live(  # pragma: no cover -- live I/O, exercised by smoke
    profile: str, groups: tuple[TableGroup, ...]
) -> tuple[ScopeManifest, tuple[CaptureResult, ...], tuple[str, ...]]:
    """List artifact names for custom scopes across covered table groups.

    NOT a full capture -- the checklist only needs each artifact's name/type/
    scope, so this issues one lightweight ``list_records`` per table (sys_id,
    name field, sys_scope) instead of a full config capture (every flow's
    inputs/logic, every topic's blocks, all child records) -- orders of
    magnitude faster. The client carries a token refresh callback to survive
    the ~30-minute OAuth cap.
    """
    _registry, meta, token, _expiry = _acquire_token(profile)

    async def _refresh() -> tuple[str, datetime]:
        _r, _m, new_token, new_expiry = _acquire_token(profile)
        return new_token, new_expiry

    now = datetime.now(UTC)
    manifests: list[ScopeManifest] = []
    captures: list[CaptureResult] = []
    skipped: list[str] = []
    async with ServiceNowClient(
        instance_url=meta.url, token=token, refresh_token_callback=_refresh
    ) as client:
        with nexus_progress(console) as progress:
            task = progress.add_task("Discovering scopes...", total=None)

            def on_progress(completed: int, total: int, message: str) -> None:
                progress.update(
                    task,
                    description=message,
                    total=total if total > 0 else None,
                    completed=completed,
                )

            async def _list_table(spec: TableSpec, query: str) -> list[ConfigRecord]:
                """List all records of one table matching a scope query.

                Args:
                    spec: Table being listed.
                    query: Encoded sysparm query restricting to target scopes.

                Returns:
                    Every matching record as a ConfigRecord, paged until exhausted.
                """
                rows: list[ConfigRecord] = []
                offset = 0
                while True:
                    batch = await client.list_records(
                        spec.name,
                        query=query,
                        limit=_PAGE_SIZE,
                        offset=offset,
                        fields=f"sys_id,{spec.name_field},{spec.scope_field}",
                    )
                    rows.extend(
                        ConfigRecord(
                            sys_id=_ref_value(row.get("sys_id")),
                            table=spec.name,
                            scope_sys_id=_ref_value(row.get(spec.scope_field)),
                            scope_name="",
                            captured_at=now,
                            fields={"name": _ref_value(row.get(spec.name_field))},
                            parent_sys_id=None,
                        )
                        for row in batch
                    )
                    if len(batch) < _PAGE_SIZE:
                        break
                    offset += _PAGE_SIZE
                return rows

            discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
            for group in groups:
                manifest = await discoverer.discover(profile, group.key, on_progress=on_progress)
                manifests.append(manifest)
                # A replatform checklist cares about CUSTOM scoped apps, plus
                # customer-created/modified records in the global scope -- not
                # the hundreds of out-of-box global and vendor-scoped records.
                custom_ids = [
                    entry.sys_id
                    for entry in manifest.scopes
                    if entry.scope.startswith(_CUSTOM_PREFIXES)
                ]
                global_ids = [entry.sys_id for entry in manifest.scopes if entry.scope == "global"]
                records: list[ConfigRecord] = []
                if custom_ids or global_ids:
                    for spec in group.tables:
                        progress.update(task, description=f"Listing {spec.display}...", total=None)
                        try:
                            if custom_ids:
                                records.extend(
                                    await _list_table(
                                        spec,
                                        _scope_query(
                                            spec, ",".join(custom_ids), customer_only=False
                                        ),
                                    )
                                )
                            if global_ids:
                                records.extend(
                                    await _list_table(
                                        spec,
                                        _scope_query(
                                            spec, ",".join(global_ids), customer_only=True
                                        ),
                                    )
                                )
                        except SNClientError as exc:
                            # A table absent on this instance (e.g. ai_skill
                            # without NowAssist) returns HTTP 400/404 -- skip
                            # just those. Auth (401/403), rate-limit (429), and
                            # any other error must raise so a partial listing
                            # is never shown as complete.
                            if exc.status_code not in (400, 404):
                                raise
                            skipped.append(spec.name)
                            log.debug("replatform: skipping absent table %s: %s", spec.name, exc)
                captures.append(
                    CaptureResult(
                        instance_id=profile,
                        captured_at=now,
                        scope_ids=tuple(custom_ids + global_ids),
                        table_group=group.key,
                        records=tuple(records),
                    )
                )
    return _merge_manifests(tuple(manifests)), tuple(captures), tuple(skipped)


def _ref_value(raw: object) -> str:
    """Extract a string from a Table API field value (handles reference dicts).

    With ``sysparm_display_value=false`` a reference field (e.g. ``sys_scope``)
    arrives as ``{"link": ..., "value": "<sys_id>"}``; plain fields arrive as
    strings. This returns the underlying string in both cases.

    Args:
        raw: A raw field value from a Table API row.

    Returns:
        The field's string value, or "" when absent.
    """
    if isinstance(raw, dict):
        return str(cast("dict[str, object]", raw).get("value", ""))
    if raw is None:
        return ""
    return str(raw)


@assess_app.command("inventory")
def assess_inventory(  # pragma: no cover -- thin Typer wrapper over run_inventory
    profile: Annotated[str, typer.Argument(help="Instance profile to inventory")],
    out: Annotated[
        str, typer.Option("--out", help="Write the inventory as JSON to this path")
    ] = "",
    domain_map: Annotated[
        str,
        typer.Option("--domain-map", help="YAML file mapping scope keys to business domains"),
    ] = "",
    group: Annotated[
        list[str] | None,
        typer.Option("--group", help="Restrict to table group(s) (repeatable; default: all)"),
    ] = None,
) -> None:
    """Classify one instance's captured config into a use-case inventory."""
    paths = NexusPaths.from_env()
    code = run_inventory(
        profile=profile,
        out=Path(out) if out else None,
        render_context=_render_context,
        collaborators=default_replatform_collaborators(
            paths, groups=resolve_groups(group or []), overrides=parse_domain_map(domain_map)
        ),
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
    out_json: Annotated[
        str,
        typer.Option(
            "--out-json", help="Write the checklist as MigrationChecklist JSON to this path"
        ),
    ] = "",
    domain_map: Annotated[
        str,
        typer.Option("--domain-map", help="YAML file mapping scope keys to business domains"),
    ] = "",
    group: Annotated[
        list[str] | None,
        typer.Option("--group", help="Restrict to table group(s) (repeatable; default: all)"),
    ] = None,
) -> None:
    """Diff two instances into a bi-directional replatform checklist."""
    paths = NexusPaths.from_env()
    code = run_migration(
        from_profile=from_profile,
        to_profile=to_profile,
        aliases=parse_scope_aliases(scope_alias or []),
        out=Path(out) if out else None,
        out_json=Path(out_json) if out_json else None,
        render_context=_render_context,
        collaborators=default_replatform_collaborators(
            paths, groups=resolve_groups(group or []), overrides=parse_domain_map(domain_map)
        ),
    )
    raise typer.Exit(code)
