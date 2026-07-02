# src/nexus/cli/migrate_wiring.py
# Production live-wiring (ServiceNow I/O) for `nexus migrate plan`/`--recheck`.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Live ServiceNow wiring for the `migrate plan`/`--recheck` collaborator seams.

Split out of ``commands_migrate.py`` (Story 06 prep, file-size carry-forward)
so that module stays under its line budget as the recheck feature (Story 06)
adds more CLI orchestration code. This module owns every live-I/O helper
``commands_migrate.py`` needs -- schema-graph fetch, capture orchestration,
client construction, and the instance-wide baseline/recheck listing -- plus
the injectable collaborator seam types (``PlanCollaborators``,
``RecheckCollaborators``) and their production ``default_*`` wire-ups.
Every live-I/O function here is ``# pragma: no cover`` -- tests inject fake
collaborators (``tests/cli/test_migrate_plan_cmd.py``,
``tests/cli/test_migrate_plan_recheck_cmd.py``), never a live client.
"""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from nexus.capture.models import CaptureResult
from nexus.capture.scope import ScopeDiscoverer
from nexus.capture.tables import DEFAULT_TABLE_GROUPS, TableGroup, TableSpec
from nexus.cli.auth import acquire_token as _acquire_token
from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.connectors.servicenow.errors import SNClientError
from nexus.migrate.capture_bridge import build_capture_for_selection, natural_key_segment
from nexus.migrate.models import BaselineEntry, Selection
from nexus.schema.models import FieldDef, ReferenceEdge, SchemaGraph, TableDef

__all__ = [
    "PlanCollaborators",
    "RecheckCollaborators",
    "default_plan_collaborators",
    "default_recheck_collaborators",
]

log = logging.getLogger(__name__)

# sys_dictionary fetch shape for the live schema-graph helper -- mirrors
# scripts/spike_s0_fetch_schema_edges.py's proven batching/paging constants.
_DICT_FIELDS = "name,element,column_label,internal_type,reference,mandatory"
_IN_BATCH = 40
_PAGE_LIMIT = 5000
_SCHEMA_AREA_KEY = "migrate-plan-selection-tables"

# Baseline/recheck instance-wide listing (Story 06) -- mirrors
# commands_assess_replatform.py's lightweight-listing constants.
_CUSTOM_PREFIXES = ("x_", "u_")
_PAGE_SIZE = 1000
_FINGERPRINT_FIELD = "sys_updated_on"


def _empty_baselines(
    _selection: Selection,
) -> tuple[tuple[BaselineEntry, ...], tuple[BaselineEntry, ...]]:
    """Default ``PlanCollaborators.build_baselines`` -- no baseline listing.

    Lets Story 05 test fixtures construct a ``PlanCollaborators`` without
    caring about baselines; ``run_plan`` still records empty baselines on
    the assembled plan in that case.

    Args:
        _selection: Unused -- the default never lists anything.

    Returns:
        A pair of empty BaselineEntry tuples.
    """
    return (), ()


@dataclass(frozen=True, slots=True)
class PlanCollaborators:
    """Injectable seam for `migrate plan`.

    Attributes:
        build_captures: Given a Selection, return CaptureResults covering
            BOTH the source instance (``selection.source_profile``) and the
            target instance (``selection.target_profile``) in one tuple --
            ``build_closure`` filters it by ``instance_id`` internally.
        build_schema_graph: Given a Selection, return the offline
            reference-edge SchemaGraph closure walks the source side over.
        build_baselines: Given a Selection, return instance-wide
            (source, target) BaselineEntry listings (Story 06) covering the
            same universe a later ``--recheck`` re-inventory covers.
            Defaults to empty listings so Story 05 fixtures that do not care
            about baselines need no change.
    """

    build_captures: Callable[[Selection], tuple[CaptureResult, ...]]
    build_schema_graph: Callable[[Selection], SchemaGraph]
    build_baselines: Callable[
        [Selection], tuple[tuple[BaselineEntry, ...], tuple[BaselineEntry, ...]]
    ] = _empty_baselines


@dataclass(frozen=True, slots=True)
class RecheckCollaborators:
    """Injectable seam for `migrate plan --recheck` (Story 06).

    Attributes:
        build_listings: Given the plan's source and target profiles, return
            fresh instance-wide (source, target) BaselineEntry listings
            covering the same universe as the plan's own baselines.
    """

    build_listings: Callable[
        [str, str], tuple[tuple[BaselineEntry, ...], tuple[BaselineEntry, ...]]
    ]


def _dict_cell(row: dict[str, object], key: str) -> str:  # pragma: no cover -- live I/O helper
    """Extract a Table API cell's scalar value (reference cells arrive as dicts)."""
    raw = row.get(key)
    if isinstance(raw, dict):
        return str(cast("dict[str, object]", raw).get("value", ""))
    return "" if raw is None else str(raw)


async def _fetch_reference_dictionary_rows(  # pragma: no cover -- live I/O
    client: ServiceNowClient, tables: tuple[str, ...]
) -> list[dict[str, object]]:
    """Batched, paginated ``sys_dictionary`` fetch restricted to reference fields.

    Mirrors ``scripts/spike_s0_fetch_schema_edges.py``'s proven fetch shape,
    generalized to an arbitrary table set (the selection's named tables)
    instead of the spike's fixed 9-table artifact list.

    Args:
        client: Open ServiceNowClient for the source instance.
        tables: Table API names to restrict the query to.

    Returns:
        Concatenated raw sys_dictionary rows across all batches and pages.
    """
    rows: list[dict[str, object]] = []
    uniq = sorted(set(tables))
    for i in range(0, len(uniq), _IN_BATCH):
        batch = uniq[i : i + _IN_BATCH]
        query = f"nameIN{','.join(batch)}^elementISNOTEMPTY^referenceISNOTEMPTY"
        offset = 0
        while True:
            page = await client.list_records(
                "sys_dictionary",
                query=query,
                fields=_DICT_FIELDS,
                limit=_PAGE_LIMIT,
                offset=offset,
            )
            rows.extend(page)
            if len(page) < _PAGE_LIMIT:
                break
            offset += _PAGE_LIMIT
    return rows


def _schema_graph_from_dictionary_rows(  # pragma: no cover -- live I/O
    instance_id: str,
    tables: tuple[str, ...],
    rows: list[dict[str, object]],
    discovered_at: datetime,
) -> SchemaGraph:
    """Build a SchemaGraph covering ``tables`` from raw sys_dictionary rows.

    Minimal equivalent of ``scripts/spike_s0_fetch_schema_edges.py``'s
    ``_build_schema_graph``, generalized to the selection's own table set
    instead of a fixed artifact-table list.

    Args:
        instance_id: Profile the rows were fetched from.
        tables: The selection's named tables (become in-scope TableDefs).
        rows: Raw sys_dictionary rows from ``_fetch_reference_dictionary_rows``.
        discovered_at: UTC timestamp for the graph.

    Returns:
        A SchemaGraph covering ``tables`` and their reference targets.
    """
    table_set = set(tables)
    fields_by_table: dict[str, list[FieldDef]] = {}
    ref_edges: list[ReferenceEdge] = []
    referenced_tables: set[str] = set()
    for row in rows:
        table = _dict_cell(row, "name")
        elem = _dict_cell(row, "element")
        target = _dict_cell(row, "reference")
        if table not in table_set or not elem or not target:
            continue
        internal_type = _dict_cell(row, "internal_type") or "reference"
        fields_by_table.setdefault(table, []).append(
            FieldDef(
                name=elem,
                label=_dict_cell(row, "column_label"),
                type=internal_type,
                reference_target=target,
                mandatory=_dict_cell(row, "mandatory") == "true",
            )
        )
        ref_edges.append(
            ReferenceEdge(
                from_table=table,
                field=elem,
                to_table=target,
                cross_scope=False,
                is_list=internal_type == "glide_list",
            )
        )
        referenced_tables.add(target)
    ref_edges.sort(key=lambda edge: (edge.from_table, edge.field))

    table_defs = [
        TableDef(
            name=name,
            label=name,
            scope="",
            is_neighbor=False,
            fields=tuple(sorted(fields_by_table.get(name, ()), key=lambda field: field.name)),
        )
        for name in sorted(table_set)
    ]
    table_defs.extend(
        TableDef(name=name, label=name, scope="", is_neighbor=True)
        for name in sorted(referenced_tables - table_set)
    )
    return SchemaGraph(
        instance_id=instance_id,
        area_key=_SCHEMA_AREA_KEY,
        discovered_at=discovered_at,
        scope_keys=(),
        tables=tuple(table_defs),
        reference_edges=tuple(ref_edges),
        inheritance_edges=(),
        relationship_edges=(),
    )


async def _build_live_schema_graph(selection: Selection) -> SchemaGraph:  # pragma: no cover
    """Fetch reference-field edges for the selection's tables, live read-only.

    Args:
        selection: The curated Selection naming source-instance tables.

    Returns:
        A SchemaGraph covering exactly the selection's named tables and
        their reference targets.
    """
    tables = tuple(sorted({item.key.split("|", 2)[1] for item in selection.items}))
    _registry, meta, token, _expiry = _acquire_token(selection.source_profile)
    async with ServiceNowClient(instance_url=meta.url, token=token) as client:
        rows = await _fetch_reference_dictionary_rows(client, tables)
    return _schema_graph_from_dictionary_rows(
        selection.source_profile, tables, rows, datetime.now(UTC)
    )


async def _capture_for_profile(  # pragma: no cover -- live I/O
    selection: Selection, profile: str
) -> tuple[CaptureResult, ...]:
    """Open a client for ``profile`` and run build_capture_for_selection.

    Args:
        selection: A Selection whose ``source_profile`` is ``profile`` --
            the instance to capture from.
        profile: Instance profile to acquire a token/connection for.

    Returns:
        The CaptureResults ``build_capture_for_selection`` returns.
    """
    _registry, meta, token, _expiry = _acquire_token(profile)
    async with ServiceNowClient(instance_url=meta.url, token=token) as client:
        return await build_capture_for_selection(client, selection, DEFAULT_TABLE_GROUPS)


async def _build_live_captures(
    selection: Selection,
) -> tuple[CaptureResult, ...]:  # pragma: no cover
    """Fetch full CaptureResults for the selection from BOTH instances.

    Args:
        selection: The curated Selection naming source-instance artifacts.

    Returns:
        CaptureResults covering ``source_profile`` and ``target_profile``,
        via ``build_capture_for_selection`` against each instance in turn
        (the target side reuses the same bridge with a mirrored Selection
        whose ``source_profile`` is the target profile).
    """
    source_captures = await _capture_for_profile(selection, selection.source_profile)
    target_selection = selection.model_copy(update={"source_profile": selection.target_profile})
    target_captures = await _capture_for_profile(target_selection, selection.target_profile)
    return (*source_captures, *target_captures)


def _ref_value(raw: object) -> str:  # pragma: no cover -- live I/O helper
    """Extract a string from a Table API field value (handles reference dicts).

    Mirrors ``commands_assess_replatform._ref_value`` byte-for-byte;
    duplicated rather than imported since it is module-private there and
    pyright's ``reportPrivateUsage`` rejects a cross-module private import
    under this project's strict config (see capture_bridge.py's docstring
    for the established precedent of this duplication pattern).

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


async def _list_baseline_table(  # pragma: no cover -- live I/O
    client: ServiceNowClient,
    spec: TableSpec,
    scope_key_by_sys_id: dict[str, str],
    query: str,
) -> list[BaselineEntry]:
    """List one table's records matching ``query`` as BaselineEntry rows.

    Args:
        client: Open ServiceNowClient for the instance being listed.
        spec: Table being listed.
        scope_key_by_sys_id: Scope sys_id -> technical scope key, so each
            row's natural key matches Selection/PlanItem keys exactly.
        query: Encoded sysparm query restricting to target scopes.

    Returns:
        One BaselineEntry per matching row, paged until exhausted.
    """
    rows: list[BaselineEntry] = []
    offset = 0
    while True:
        batch = await client.list_records(
            spec.name,
            query=query,
            limit=_PAGE_SIZE,
            offset=offset,
            fields=f"sys_id,{spec.name_field},{spec.scope_field},{_FINGERPRINT_FIELD}",
        )
        for row in batch:
            scope_sys_id = _ref_value(row.get(spec.scope_field))
            scope_key = scope_key_by_sys_id.get(scope_sys_id, scope_sys_id)
            name = _ref_value(row.get(spec.name_field))
            segment = natural_key_segment(name) or _ref_value(row.get("sys_id"))
            rows.append(
                BaselineEntry(
                    key=f"{scope_key}|{spec.name}|{segment}",
                    fingerprint=_ref_value(row.get(_FINGERPRINT_FIELD)),
                )
            )
        if len(batch) < _PAGE_SIZE:
            break
        offset += _PAGE_SIZE
    return rows


async def _list_baseline_live(  # pragma: no cover -- live I/O
    profile: str, groups: tuple[TableGroup, ...]
) -> tuple[BaselineEntry, ...]:
    """Lightweight instance-wide natural-key + sys_updated_on listing (Story 06).

    Mirrors ``commands_assess_replatform._list_artifacts_live``'s scope
    discovery and custom/global-scope filtering (Resolution 2: the baseline
    and a later ``--recheck`` re-inventory must cover the same universe --
    the plan's selection-scoped captures cannot be the baseline, or
    everything outside the selection would report as "added"), additionally
    requesting ``sys_updated_on`` as each artifact's fingerprint.

    Args:
        profile: Instance profile to list.
        groups: Table groups to cover (the standard replatform groups).

    Returns:
        BaselineEntry rows sorted by (key, fingerprint) -- deterministic for
        byte-stable plan assembly.
    """
    _registry, meta, token, _expiry = _acquire_token(profile)

    async def _refresh() -> tuple[str, datetime]:
        _r, _m, new_token, new_expiry = _acquire_token(profile)
        return new_token, new_expiry

    entries: list[BaselineEntry] = []
    async with ServiceNowClient(
        instance_url=meta.url, token=token, refresh_token_callback=_refresh
    ) as client:
        discoverer = ScopeDiscoverer(client, DEFAULT_TABLE_GROUPS)
        for group in groups:
            manifest = await discoverer.discover(profile, group.key)
            scope_key_by_sys_id = {entry.sys_id: entry.scope for entry in manifest.scopes}
            custom_ids = [
                entry.sys_id
                for entry in manifest.scopes
                if entry.scope.startswith(_CUSTOM_PREFIXES)
            ]
            global_ids = [entry.sys_id for entry in manifest.scopes if entry.scope == "global"]
            if not (custom_ids or global_ids):
                continue
            for spec in group.tables:
                try:
                    if custom_ids:
                        entries.extend(
                            await _list_baseline_table(
                                client,
                                spec,
                                scope_key_by_sys_id,
                                f"{spec.scope_field}IN{','.join(custom_ids)}",
                            )
                        )
                    if global_ids:
                        entries.extend(
                            await _list_baseline_table(
                                client,
                                spec,
                                scope_key_by_sys_id,
                                f"{spec.scope_field}IN{','.join(global_ids)}"
                                "^sys_customer_update=true",
                            )
                        )
                except SNClientError as exc:
                    # A table absent on this instance -- skip just that one;
                    # auth/rate-limit/other errors must still raise.
                    if exc.status_code not in (400, 404):
                        raise
                    log.debug("recheck: skipping absent table %s: %s", spec.name, exc)
    return tuple(sorted(entries, key=lambda entry: (entry.key, entry.fingerprint)))


def _live_baselines(  # pragma: no cover -- live I/O
    source_profile: str, target_profile: str
) -> tuple[tuple[BaselineEntry, ...], tuple[BaselineEntry, ...]]:
    """Fetch instance-wide baseline listings for both instances, live read-only.

    Args:
        source_profile: Source instance profile.
        target_profile: Target instance profile.

    Returns:
        (source_entries, target_entries).
    """
    groups = tuple(DEFAULT_TABLE_GROUPS.values())
    source = asyncio.run(_list_baseline_live(source_profile, groups))
    target = asyncio.run(_list_baseline_live(target_profile, groups))
    return source, target


def default_plan_collaborators() -> PlanCollaborators:  # pragma: no cover -- production wiring
    """Production wire-up: live captures + a live schema graph for `migrate plan`.

    Returns:
        A PlanCollaborators whose ``build_captures`` fetches full
        CaptureResults from both instances, ``build_schema_graph`` fetches
        reference edges for exactly the selection's named tables, and
        ``build_baselines`` fetches instance-wide baseline listings for both
        instances (Story 06).
    """
    return PlanCollaborators(
        build_captures=lambda selection: asyncio.run(_build_live_captures(selection)),
        build_schema_graph=lambda selection: asyncio.run(_build_live_schema_graph(selection)),
        build_baselines=lambda selection: _live_baselines(
            selection.source_profile, selection.target_profile
        ),
    )


def default_recheck_collaborators() -> RecheckCollaborators:  # pragma: no cover
    """Production wire-up: live instance-wide listings for `migrate plan --recheck`.

    Returns:
        A RecheckCollaborators whose ``build_listings`` fetches fresh
        instance-wide baseline listings for both instances.
    """
    return RecheckCollaborators(build_listings=_live_baselines)
