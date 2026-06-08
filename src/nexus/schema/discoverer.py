# src/nexus/schema/discoverer.py
# Reverse-engineers a live SN data dictionary into a SchemaGraph.
# Author: Pierre Grothe
# Date: 2026-06-08
"""SchemaDiscoverer: sys_scope -> sys_db_object -> sys_dictionary / sys_relationship."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import cast

from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
from nexus.schema.areas import DEFAULT_AREAS, SchemaArea
from nexus.schema.errors import AreaNotFoundError, ScopeNotFoundError
from nexus.schema.models import (
    FieldDef,
    InheritanceEdge,
    ReferenceEdge,
    RelationshipEdge,
    SchemaGraph,
    TableDef,
)

log = logging.getLogger(__name__)

__all__ = ["SchemaDiscoverer", "cell"]

_IN_BATCH = 40
_OUT = "__out"  # sentinel scope for out-of-area tables; never a real scope key


def cell(row: Mapping[str, object], key: str) -> str:
    """Extract a Table API cell's scalar value.

    Reference cells are dicts (``{"link"|"display_value", "value"}``); take
    ``value``. Plain scalars return as a string. Missing keys return "".

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


class SchemaDiscoverer:
    """Builds a SchemaGraph for one area from a live instance.

    Args:
        client: Open ServiceNow client (read-only Table API).
        areas: Area registry keyed by area key.
        clock: Callable returning the current UTC time (injectable for tests).
    """

    def __init__(
        self,
        client: ServiceNowClientProtocol,
        areas: Mapping[str, SchemaArea] = DEFAULT_AREAS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Initialize with a client, area registry, and clock."""
        self._client = client
        self._areas = areas
        self._clock = clock

    async def discover(self, instance_id: str, area_key: str) -> SchemaGraph:
        """Reverse-engineer the data dictionary for one area.

        Args:
            instance_id: Registered instance profile name.
            area_key: Key into the area registry.

        Returns:
            A SchemaGraph of tables and reference/inheritance/relationship edges.

        Raises:
            AreaNotFoundError: If area_key is unknown.
            ScopeNotFoundError: If none of the area's scopes resolve.
        """
        if area_key not in self._areas:
            raise AreaNotFoundError(area_key)
        area = self._areas[area_key]
        scope_keys = [s.scope for s in area.scopes]

        scope_rows = await self._client.list_records(
            "sys_scope", query=f"scopeIN{','.join(scope_keys)}", fields="sys_id,scope", limit=200
        )
        key_by_id = {cell(r, "sys_id"): cell(r, "scope") for r in scope_rows if cell(r, "sys_id")}
        present = set(key_by_id.values())
        for missing in (k for k in scope_keys if k not in present):
            log.warning("scope %r absent on %s -- skipping", missing, instance_id)
        if not key_by_id:
            raise ScopeNotFoundError(scope_keys, instance_id)

        # In-scope tables: membership derived from each row's sys_scope.
        db_rows = await self._batched_in(
            "sys_db_object", "sys_scope", list(key_by_id),
            fields="sys_id,name,label,super_class,sys_scope",
        )
        name_by_id: dict[str, str] = {}
        label_by_name: dict[str, str] = {}
        meta: dict[str, tuple[str, str]] = {}  # name -> (scope_key, super_id)
        for r in db_rows:
            name = cell(r, "name")
            tid = cell(r, "sys_id")
            scope_id = cell(r, "sys_scope")
            if not name or not tid or scope_id not in key_by_id:
                continue
            name_by_id[tid] = name
            label_by_name[name] = cell(r, "label")
            meta[name] = (key_by_id[scope_id], cell(r, "super_class"))
        in_scope = sorted(meta)

        # Resolve super_class parent sys_ids to names (+ labels).
        parent_ids = sorted({s for _, s in meta.values() if s and s not in name_by_id})
        if parent_ids:
            for r in await self._batched_in(
                "sys_db_object", "sys_id", parent_ids, fields="sys_id,name,label"
            ):
                pname = cell(r, "name")
                name_by_id[cell(r, "sys_id")] = pname
                label_by_name.setdefault(pname, cell(r, "label"))

        # Fields + reference edges.
        dict_rows = await self._batched_in(
            "sys_dictionary", "name", in_scope,
            fields="name,element,column_label,reference,mandatory", suffix="^elementISNOTEMPTY",
        )
        fields_by: dict[str, list[FieldDef]] = {}
        ref_edges: list[ReferenceEdge] = []
        for r in dict_rows:
            tname = cell(r, "name")
            elem = cell(r, "element")
            if tname not in meta or not elem:
                continue
            ref = cell(r, "reference")  # reference.value IS the target table name
            fields_by.setdefault(tname, []).append(
                FieldDef(
                    name=elem,
                    label=cell(r, "column_label"),
                    type="reference" if ref else "field",
                    reference_target=ref or None,
                    mandatory=cell(r, "mandatory") == "true",
                )
            )
            if ref:
                cross = meta[tname][0] != meta.get(ref, (_OUT, ""))[0]
                ref_edges.append(
                    ReferenceEdge(from_table=tname, field=elem, to_table=ref, cross_scope=cross)
                )

        # Inheritance edges + neighbor collection.
        inh_edges: list[InheritanceEdge] = []
        neighbors: set[str] = set()
        for name, (scope_key, super_id) in meta.items():
            parent = name_by_id.get(super_id, "")
            if not parent:
                continue
            cross = scope_key != meta.get(parent, (_OUT, ""))[0]
            inh_edges.append(InheritanceEdge(table=name, extends=parent, cross_scope=cross))
            if parent not in meta:
                neighbors.add(parent)
        neighbors.update(e.to_table for e in ref_edges if e.to_table not in meta)

        tables: list[TableDef] = [
            TableDef(
                name=name,
                label=label_by_name.get(name, name),
                scope=scope_key,
                super_class=name_by_id.get(super_id) or None,
                is_neighbor=False,
                fields=tuple(fields_by.get(name, ())),
            )
            for name, (scope_key, super_id) in meta.items()
        ]
        tables.extend(
            TableDef(name=nb, label=label_by_name.get(nb, nb), scope="", is_neighbor=True)
            for nb in sorted(neighbors)
        )

        rel_rows = await self._client.list_records(
            "sys_relationship",
            query=f"apply_toIN{','.join(in_scope)}^ORquery_fromIN{','.join(in_scope)}",
            fields="name,apply_to,query_from",
            limit=2000,
        )
        rel_edges = [
            RelationshipEdge(
                name=cell(r, "name"), apply_to=cell(r, "apply_to"), query_from=cell(r, "query_from")
            )
            for r in rel_rows
            if cell(r, "name")
        ]

        return SchemaGraph(
            instance_id=instance_id,
            area_key=area_key,
            discovered_at=self._clock(),
            scope_keys=tuple(sorted(present)),
            tables=tuple(tables),
            reference_edges=tuple(ref_edges),
            inheritance_edges=tuple(inh_edges),
            relationship_edges=tuple(rel_edges),
        )

    async def _batched_in(
        self,
        table: str,
        field: str,
        values: list[str],
        *,
        fields: str,
        suffix: str = "",
    ) -> list[dict[str, object]]:
        """Run ``{field}IN{batch}`` queries in batches of _IN_BATCH.

        Args:
            table: Table to query.
            field: Field for the IN clause.
            values: Values to batch.
            fields: Comma-separated fields to return.
            suffix: Extra encoded-query fragment appended to each batch query.

        Returns:
            Concatenated rows across all batches.
        """
        rows: list[dict[str, object]] = []
        uniq = sorted({v for v in values if v})
        for i in range(0, len(uniq), _IN_BATCH):
            batch = uniq[i : i + _IN_BATCH]
            rows.extend(
                await self._client.list_records(
                    table, query=f"{field}IN{','.join(batch)}{suffix}", fields=fields, limit=5000
                )
            )
        return rows
