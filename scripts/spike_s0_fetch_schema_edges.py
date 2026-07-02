# scripts/spike_s0_fetch_schema_edges.py
# One-time read-only fetch of reference-field edges for the S0 closure spike.
# Author: Pierre Grothe
# Date: 2026-07-02
"""Fetch sys_dictionary reference-field rows for the 9 artifact tables.

This is the live half of the S0 closure-scale spike (Story 00 of the
migration-planner epic). ``scripts/spike_s0_closure_scale.py`` is the pure,
offline measurement harness; this script exists only to populate its input
schema-graph archive, once, from a real instance.

Deliberately narrower than ``nexus.schema.discoverer.SchemaDiscoverer``:
that reverse-engineers a whole ``sys_scope`` (and the 9 artifact tables here
live in the ``global`` scope, which owns the entire platform dictionary --
discovering it would pull orders of magnitude more rows than this spike
needs). Instead this issues exactly one batched, paginated query against
``sys_dictionary`` restricted to the 9 artifact tables and to reference
fields only (``elementISNOTEMPTY^referenceISNOTEMPTY``), mirroring the
paging/batching style of ``SchemaDiscoverer._batched_in``.

Read-only: only ``ServiceNowClient.list_records`` (a GET) is ever called.
Nothing is written to the instance.

Usage:
    poetry run python scripts/spike_s0_fetch_schema_edges.py --profile alectri
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from nexus.cli.auth import acquire_token
from nexus.connectors.servicenow.client import ServiceNowClient
from nexus.schema.archive import SchemaArchiveWriter
from nexus.schema.models import FieldDef, ReferenceEdge, SchemaGraph, TableDef

__all__ = ["main"]

ARTIFACT_TABLES: tuple[str, ...] = (
    "sys_script",
    "sys_script_include",
    "sys_ui_policy",
    "sys_script_client",
    "sys_ui_action",
    "sysauto_script",
    "sys_hub_flow",
    "sys_hub_action_type_definition",
    "wf_workflow",
)

# Never touch any profile other than the two demo instances used across this
# epic's spikes -- this fetch is read-only, but "never touch any profile
# other than alectri/retail" is a hard limit from the story brief.
_ALLOWED_PROFILES = frozenset({"alectri", "retail"})
_AREA_KEY = "s0-platform-artifacts"
_IN_BATCH = 40
_PAGE_LIMIT = 5000
_DICT_FIELDS = "name,element,column_label,internal_type,reference,mandatory"
_DEFAULT_ARCHIVE_ROOT = Path("artifacts/replatform-proof")


def _cell(row: Mapping[str, object], key: str) -> str:
    """Extract a Table API cell's scalar value.

    Reference cells arrive as ``{"link"|"display_value", "value"}`` dicts;
    take ``value``. Plain scalars return as a string. Missing keys return "".

    Args:
        row: A Table API result row.
        key: Column name.

    Returns:
        The scalar value (sys_id or table name for references), else "".
    """
    raw = row.get(key)
    if isinstance(raw, dict):
        return str(cast("dict[str, object]", raw).get("value", ""))
    return "" if raw is None else str(raw)


async def _fetch_reference_dictionary_rows(
    client: ServiceNowClient, tables: tuple[str, ...]
) -> list[dict[str, object]]:
    """Batched, paginated ``sys_dictionary`` fetch for reference fields only.

    Mirrors ``SchemaDiscoverer._batched_in``: values are chunked into
    batches of ``_IN_BATCH`` for URL-length safety, and each batch is paged
    in ``_PAGE_LIMIT`` chunks until a short page signals the last page.

    Args:
        client: Open ServiceNowClient (read-only Table API).
        tables: Artifact table names to restrict the query to.

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


def _build_schema_graph(
    instance_id: str, rows: list[dict[str, object]], discovered_at: datetime
) -> SchemaGraph:
    """Build a SchemaGraph of the 9 artifact tables from raw dictionary rows.

    Every artifact table becomes an in-scope ``TableDef`` carrying only the
    reference ``FieldDef``s the fetch retrieved (the query already restricts
    to ``referenceISNOTEMPTY``, so no other columns were fetched). Every
    distinct reference target not itself one of the 9 tables becomes a
    neighbor ``TableDef``. Inheritance and relationship edges are left empty
    -- this spike only needs reference-field closure. No sys_scope
    resolution was performed, so ``cross_scope`` is uniformly False and
    table labels fall back to the table name.

    Args:
        instance_id: Profile the rows were fetched from.
        rows: Raw sys_dictionary rows from ``_fetch_reference_dictionary_rows``.
        discovered_at: UTC timestamp for the graph.

    Returns:
        A SchemaGraph covering the 9 artifact tables and their reference
        targets.
    """
    fields_by_table: dict[str, list[FieldDef]] = {}
    ref_edges: list[ReferenceEdge] = []
    referenced_tables: set[str] = set()
    for row in rows:
        table = _cell(row, "name")
        elem = _cell(row, "element")
        target = _cell(row, "reference")
        if table not in ARTIFACT_TABLES or not elem or not target:
            continue
        internal_type = _cell(row, "internal_type") or "reference"
        fields_by_table.setdefault(table, []).append(
            FieldDef(
                name=elem,
                label=_cell(row, "column_label"),
                type=internal_type,
                reference_target=target,
                mandatory=_cell(row, "mandatory") == "true",
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
    ref_edges.sort(key=lambda e: (e.from_table, e.field))

    tables: list[TableDef] = [
        TableDef(
            name=name,
            label=name,
            scope="",
            is_neighbor=False,
            fields=tuple(sorted(fields_by_table.get(name, ()), key=lambda f: f.name)),
        )
        for name in ARTIFACT_TABLES
    ]
    tables.extend(
        TableDef(name=name, label=name, scope="", is_neighbor=True)
        for name in sorted(referenced_tables - set(ARTIFACT_TABLES))
    )

    return SchemaGraph(
        instance_id=instance_id,
        area_key=_AREA_KEY,
        discovered_at=discovered_at,
        scope_keys=(),
        tables=tuple(tables),
        reference_edges=tuple(ref_edges),
        inheritance_edges=(),
        relationship_edges=(),
    )


async def _run(profile: str, archive_root: Path) -> Path:
    """Fetch reference edges for the 9 artifact tables and archive them.

    Args:
        profile: Registered instance profile (must be alectri or retail).
        archive_root: Directory SchemaArchiveWriter writes under.

    Returns:
        Path to the written schema archive JSON.

    Raises:
        ValueError: If profile is not alectri or retail.
    """
    if profile not in _ALLOWED_PROFILES:
        raise ValueError(f"profile must be one of {sorted(_ALLOWED_PROFILES)}, got {profile!r}")
    _registry, meta, token, _expiry = acquire_token(profile)
    async with ServiceNowClient(instance_url=meta.url, token=token) as client:
        rows = await _fetch_reference_dictionary_rows(client, ARTIFACT_TABLES)
    graph = _build_schema_graph(profile, rows, datetime.now(UTC))
    path = SchemaArchiveWriter(archive_root).write(graph)
    print(
        f"Fetched {len(graph.reference_edges)} reference edges "
        f"across {len(graph.tables)} tables ({len(rows)} raw dictionary rows)."
    )
    print(f"Wrote schema archive to {path}")
    return path


def main() -> int:
    """Parse CLI args and run the one-time reference-edge fetch.

    Returns:
        Process exit code (always 0 on success; exceptions propagate).
    """
    parser = argparse.ArgumentParser(
        description="One-time read-only fetch of reference edges for the 9 artifact tables."
    )
    parser.add_argument(
        "--profile",
        default="alectri",
        choices=sorted(_ALLOWED_PROFILES),
        help="Registered instance profile to fetch from (default: alectri).",
    )
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=_DEFAULT_ARCHIVE_ROOT,
        help="Directory the schema archive is written under (default: artifacts/replatform-proof).",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.profile, args.archive_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
