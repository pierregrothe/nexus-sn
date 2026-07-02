# tests/fakes/migrate_closure.py
# Builders for closure/planner test fixtures (story 04).
# Author: Pierre Grothe
# Date: 2026-07-02

"""Factory helpers for nexus.migrate.closure / nexus.migrate.planner tests.

Small hand-crafted ConfigRecord/CaptureResult/SchemaGraph builders -- one
rule row at a time, not the full 30K-record dataset (that measurement is
Story 00's job). No mocks: every builder returns a real, frozen model.
"""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.capture.models import CaptureResult, ConfigRecord, SnFieldValue, SnRecord, SnRefField
from nexus.schema.models import ReferenceEdge, SchemaGraph

__all__ = [
    "DEFAULT_TS",
    "make_capture",
    "make_record",
    "make_ref",
    "make_reference_edge",
    "make_schema_graph",
]

DEFAULT_TS: datetime = datetime(2026, 7, 2, 12, 0, 0, tzinfo=UTC)


def make_ref(sys_id: str, display: str = "") -> SnRefField:
    """Build an SnRefField, defaulting display_value to the sys_id."""
    return {"value": sys_id, "display_value": display or sys_id}


def make_record(
    table: str,
    sys_id: str,
    scope: str,
    name: str,
    *,
    parent_sys_id: str | None = None,
    **ref_fields: SnFieldValue,
) -> ConfigRecord:
    """Build a ConfigRecord with a "name" field plus arbitrary extra fields.

    ``scope`` is used as both ``scope_sys_id`` and ``scope_name`` -- closure
    has no live scope-sys_id resolver, so it keys natural-key scope segments
    off ``scope_name`` directly (see closure.py's documented v1 gap); setting
    both to the same technical scope key keeps fixtures unambiguous.

    Args:
        table: Table API name.
        sys_id: Record sys_id.
        scope: Technical scope key (used for both scope fields).
        name: Value stored under the record's "name" field.
        parent_sys_id: Optional parent record sys_id (related-table rows).
        **ref_fields: Additional field values (e.g. a reference field built
            with ``make_ref``), merged alongside "name".

    Returns:
        A frozen ConfigRecord.
    """
    fields: SnRecord = {"name": name}
    fields.update(ref_fields)
    return ConfigRecord(
        sys_id=sys_id,
        table=table,
        scope_sys_id=scope,
        scope_name=scope,
        captured_at=DEFAULT_TS,
        fields=fields,
        parent_sys_id=parent_sys_id,
    )


def make_capture(
    records: tuple[ConfigRecord, ...],
    *,
    instance_id: str = "alectri",
    table_group: str = "closure_fixture",
    scope_ids: tuple[str, ...] = (),
    captured_at: datetime = DEFAULT_TS,
) -> CaptureResult:
    """Build a CaptureResult wrapping the given records."""
    return CaptureResult(
        instance_id=instance_id,
        captured_at=captured_at,
        scope_ids=scope_ids,
        table_group=table_group,
        records=records,
    )


def make_reference_edge(
    from_table: str,
    field: str,
    to_table: str,
    *,
    cross_scope: bool = False,
    is_list: bool = False,
) -> ReferenceEdge:
    """Build a ReferenceEdge with sensible defaults."""
    return ReferenceEdge(
        from_table=from_table,
        field=field,
        to_table=to_table,
        cross_scope=cross_scope,
        is_list=is_list,
    )


def make_schema_graph(
    edges: tuple[ReferenceEdge, ...] = (),
    *,
    instance_id: str = "alectri",
    area_key: str = "closure_fixture",
) -> SchemaGraph:
    """Build a SchemaGraph holding just the given reference edges."""
    return SchemaGraph(
        instance_id=instance_id,
        area_key=area_key,
        discovered_at=DEFAULT_TS,
        scope_keys=(),
        tables=(),
        reference_edges=edges,
        inheritance_edges=(),
        relationship_edges=(),
    )
