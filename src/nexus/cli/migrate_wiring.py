# src/nexus/cli/migrate_wiring.py
# Production live-wiring (ServiceNow I/O) for `nexus migrate plan`.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Live ServiceNow wiring for the `migrate plan` collaborator seam.

Split out of ``commands_migrate.py`` (Story 06 prep, file-size carry-forward)
so that module stays under its line budget as the recheck feature (Story 06)
adds more CLI orchestration code. This module owns every live-I/O helper
``commands_migrate.py`` needs for `plan` -- schema-graph fetch, capture
orchestration, client construction -- plus the injectable
``PlanCollaborators`` seam type and its production ``default_plan_collaborators``
wire-up. Every live-I/O function here is ``# pragma: no cover`` -- tests
inject a fake ``PlanCollaborators`` (``tests/cli/test_migrate_plan_cmd.py``),
never a live client.
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from nexus.capture.models import CaptureResult
from nexus.capture.tables import DEFAULT_TABLE_GROUPS
from nexus.cli.auth import acquire_token as _acquire_token
from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.migrate.capture_bridge import build_capture_for_selection
from nexus.migrate.models import Selection
from nexus.schema.models import FieldDef, ReferenceEdge, SchemaGraph, TableDef

__all__ = ["PlanCollaborators", "default_plan_collaborators"]

# sys_dictionary fetch shape for the live schema-graph helper -- mirrors
# scripts/spike_s0_fetch_schema_edges.py's proven batching/paging constants.
_DICT_FIELDS = "name,element,column_label,internal_type,reference,mandatory"
_IN_BATCH = 40
_PAGE_LIMIT = 5000
_SCHEMA_AREA_KEY = "migrate-plan-selection-tables"


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
    """

    build_captures: Callable[[Selection], tuple[CaptureResult, ...]]
    build_schema_graph: Callable[[Selection], SchemaGraph]


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


def default_plan_collaborators() -> PlanCollaborators:  # pragma: no cover -- production wiring
    """Production wire-up: live captures + a live schema graph for `migrate plan`.

    Returns:
        A PlanCollaborators whose ``build_captures`` fetches full
        CaptureResults from both instances and whose ``build_schema_graph``
        fetches reference edges for exactly the selection's named tables.
    """
    return PlanCollaborators(
        build_captures=lambda selection: asyncio.run(_build_live_captures(selection)),
        build_schema_graph=lambda selection: asyncio.run(_build_live_schema_graph(selection)),
    )
