# src/nexus/migrate/capture_bridge.py
# Selection-to-capture translation: Selection -> full CaptureResult(s).
# Author: Pierre Grothe
# Date: 2026-07-02

"""Translate a curated Selection into full-fidelity CaptureResult(s).

``build_capture_for_selection`` turns a Story-02 ``Selection`` (a checklist
of natural keys with a disposition) into real ``CaptureResult`` records
fetched fresh from the source instance, scoped to exactly the scopes and
tables named in the selection (AC4/AC5) -- never the whole table group.

Every item in ``selection.items`` is captured regardless of disposition
(include/exclude/undecided). Story 04's dependency closure must resolve
reference fields INTO excluded/undecided targets to classify them as
STRANDED_DEPENDENCY vs. auto-add, which requires their full records to
exist in the capture -- "selected artifacts" here means "artifacts named
in the Selection file", not "artifacts marked include".

Fetched root records are matched against the selection's natural keys by
recomputing each record's key from its table's ``name_field`` (tables vary,
e.g. ``sys_ui_policy`` uses ``short_description``). Matched roots keep their
full related-record graph (e.g. a matched ``sys_hub_flow``'s
``sys_hub_flow_input``/``sys_hub_flow_logic`` children) so closure can walk
real reference-field values, not just the checklist listing.

The natural-key normalization (``casefold(collapse_ws(name))``) mirrors
``nexus.replatform.classifier._normalize``/``_display_name`` byte-for-byte
by design (ADR-026: this module may consume replatform's key algorithm but
must not alter it). It is duplicated here rather than imported because
those helpers are module-private in ``nexus.replatform.classifier`` (no
public export exists) and pyright's ``reportPrivateUsage`` rejects a
cross-module private import under this project's strict config. Parity is
enforced mechanically: tests/test_migrate_capture_bridge.py asserts the
mirrors and the originals produce identical output over a battery of
tricky names, so any drift fails CI.
"""

import logging
from datetime import UTC, datetime

from nexus.capture.fetcher import ConfigFetcher
from nexus.capture.models import CaptureResult, ConfigRecord, SnFieldValue
from nexus.capture.scope import ScopeDiscoverer
from nexus.capture.tables import TableGroup
from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
from nexus.migrate.models import Selection

log = logging.getLogger(__name__)

__all__ = [
    "build_capture_for_selection",
    "field_display",
    "natural_key_segment",
    "record_natural_key",
]


def field_display(raw: SnFieldValue) -> str:
    """Coerce a captured field value to its display string.

    Mirrors ``nexus.replatform.classifier._display_name``'s extraction rule
    (reference field -> ``display_value``; scalar -> its string form) so
    natural keys computed here match keys the classifier would compute from
    the same records.

    Args:
        raw: A captured field value.

    Returns:
        The display string, or "" for None.
    """
    if isinstance(raw, dict):
        return raw["display_value"]
    if raw is None:
        return ""
    return raw if isinstance(raw, str) else str(raw)


def natural_key_segment(name: str) -> str:
    """Casefold and collapse whitespace for a stable natural-key segment.

    Must match ``nexus.replatform.classifier._normalize`` exactly -- the
    natural-key normalization must not diverge between the classifier and
    the capture layer.

    Args:
        name: Display name to normalize.

    Returns:
        The casefolded, whitespace-collapsed name.
    """
    return " ".join(name.split()).casefold()


def record_natural_key(record: ConfigRecord, name_field: str, scope_key: str) -> str:
    """Compute a record's natural key for matching against a Selection.

    Public promotion of the natural-key algorithm (Story 04 prep) so
    ``nexus.migrate.closure`` can reuse it without duplicating the logic.
    ``nexus.migrate.closure`` calls this with ``record.scope_name`` as
    ``scope_key`` since it has no live scope-sys_id resolution available
    (pure-function closure over already-captured records) -- see that
    module's docstring for the documented v1 scope-key gap this implies.

    Args:
        record: A fetched ConfigRecord.
        name_field: The record's table's display-name field.
        scope_key: The record's resolved technical scope key.

    Returns:
        The natural key, falling back to ``sys_id`` when the name is empty
        (unnamed records have no stable cross-instance identity).
    """
    name = field_display(record.fields.get(name_field, ""))
    segment = natural_key_segment(name) or record.sys_id
    return f"{scope_key}|{record.table}|{segment}"


def _normalize_scope_name(
    record: ConfigRecord, sys_id_to_scope_key: dict[str, str]
) -> ConfigRecord:
    """Correct a fetched record's scope_name to its technical scope key.

    ``ConfigFetcher`` queries with ``display_value="all"``, so a reference
    ``sys_scope`` cell arrives as a dict rather than a plain string, and
    ``ConfigFetcher._row_to_record`` falls back to stamping the raw scope
    sys_id into ``scope_name`` instead of the technical scope key --
    breaking ``record_natural_key`` downstream, which expects the technical
    key (matching how ``Selection`` keys are built). This bridge already
    resolved every selected scope's sys_id in ``sys_id_to_scope_key``
    (inverted from ``scope_sys_ids``), so it can correct the value here.

    Args:
        record: A freshly fetched ConfigRecord.
        sys_id_to_scope_key: Scope sys_id -> technical scope key, inverted
            from the scope-key -> sys_id map this bridge resolved.

    Returns:
        The record with ``scope_name`` corrected to the technical scope
        key; unchanged when its ``scope_sys_id`` has no known technical key.
    """
    scope_key = sys_id_to_scope_key.get(record.scope_sys_id)
    if scope_key is None:
        # Defensive: ConfigFetcher.fetch() stamps scope_sys_id from the
        # queried scope (see _fetch_table), never from row data -- always
        # one of the sys_ids this module resolved, so the lookup cannot
        # miss today -- kept as a guard against a future fetch path
        # supplying an unresolved scope_sys_id.
        return record  # pragma: no cover
    return record.model_copy(update={"scope_name": scope_key})


def _narrow_table_groups(
    table_groups: dict[str, TableGroup], wanted_tables: set[str]
) -> dict[str, TableGroup]:
    """Build a synthetic table-group registry limited to the wanted tables.

    Args:
        table_groups: The full table-group registry.
        wanted_tables: Table API names named by the selection's natural keys.

    Returns:
        A registry containing only groups that have at least one wanted
        table, each narrowed to just that subset of TableSpecs -- so a
        downstream ``ConfigFetcher.fetch()`` never queries a sibling table
        the selection did not name.
    """
    narrowed: dict[str, TableGroup] = {}
    for group_key, group in table_groups.items():
        specs = tuple(spec for spec in group.tables if spec.name in wanted_tables)
        if specs:
            narrowed[group_key] = TableGroup(key=group.key, display=group.display, tables=specs)
    return narrowed


async def _resolve_scope_sys_ids(
    client: ServiceNowClientProtocol,
    instance_id: str,
    narrowed: dict[str, TableGroup],
    wanted_scopes: set[str],
) -> dict[str, str]:
    """Resolve the selection's named scopes to sys_ids via ScopeDiscoverer.

    Args:
        client: Open ServiceNowClientProtocol for the source instance.
        instance_id: Source instance profile (``selection.source_profile``).
        narrowed: The narrowed table-group registry to scan for scope counts.
        wanted_scopes: Technical scope keys named by the selection.

    Returns:
        Mapping of technical scope key -> sys_id for scopes found on the
        instance. Scopes named in the selection but absent on the instance
        are logged and omitted (warn-and-continue).
    """
    discoverer = ScopeDiscoverer(client, narrowed)
    scope_sys_ids: dict[str, str] = {}
    for group_key in narrowed:
        manifest = await discoverer.discover(instance_id, group_key)
        for entry in manifest.scopes:
            if entry.scope in wanted_scopes:
                scope_sys_ids[entry.scope] = entry.sys_id

    for scope in sorted(wanted_scopes - scope_sys_ids.keys()):
        log.warning("selection scope %r not found on %s -- skipping", scope, instance_id)

    return scope_sys_ids


async def build_capture_for_selection(
    client: ServiceNowClientProtocol,
    selection: Selection,
    table_groups: dict[str, TableGroup],
) -> tuple[CaptureResult, ...]:
    """Translate a Selection into full CaptureResult(s) for exactly its artifacts.

    Args:
        client: Open ServiceNowClientProtocol for the source instance.
        selection: The curated Selection naming source-instance artifacts.
        table_groups: Table-group registry to resolve selection keys against.

    Returns:
        One CaptureResult per table group touched by the selection, holding
        full records for exactly the selection's artifacts (every item
        regardless of disposition) plus their related-record graph. Empty
        when the selection has no items, no named table is registered, or
        none of the named scopes resolve on the instance -- an empty
        selection issues no ConfigFetcher/ScopeDiscoverer calls at all.
    """
    if not selection.items:
        return ()

    wanted_scopes: set[str] = set()
    wanted_tables: set[str] = set()
    selection_keys: set[str] = set()
    for item in selection.items:
        scope, table, _name = item.key.split("|", 2)
        wanted_scopes.add(scope)
        wanted_tables.add(table)
        selection_keys.add(item.key)

    narrowed = _narrow_table_groups(table_groups, wanted_tables)
    if not narrowed:
        return ()

    instance_id = selection.source_profile
    scope_sys_ids = await _resolve_scope_sys_ids(client, instance_id, narrowed, wanted_scopes)
    if not scope_sys_ids:
        return ()

    sys_id_to_scope_key = {sys_id: scope for scope, sys_id in scope_sys_ids.items()}
    fetcher = ConfigFetcher(client, narrowed)
    now = datetime.now(UTC)
    results: list[CaptureResult] = []
    for group_key, group in narrowed.items():
        name_fields = {spec.name: spec.name_field for spec in group.tables}
        records = await fetcher.fetch(instance_id, list(scope_sys_ids.values()), group_key)

        kept: list[ConfigRecord] = []
        kept_root_ids: set[str] = set()
        for record in records:
            if record.parent_sys_id is not None:
                continue
            # ConfigFetcher.fetch() stamps scope_sys_id from the queried scope
            # (see _fetch_table), never from row data -- always one of the
            # sys_ids this module resolved, so the lookup cannot miss.
            scope_key = sys_id_to_scope_key[record.scope_sys_id]
            key = record_natural_key(record, name_fields[record.table], scope_key)
            if key in selection_keys:
                kept.append(_normalize_scope_name(record, sys_id_to_scope_key))
                kept_root_ids.add(record.sys_id)
        for record in records:
            if record.parent_sys_id is not None and record.parent_sys_id in kept_root_ids:
                kept.append(_normalize_scope_name(record, sys_id_to_scope_key))

        results.append(
            CaptureResult(
                instance_id=instance_id,
                captured_at=now,
                scope_ids=tuple(scope_sys_ids.values()),
                table_group=group_key,
                records=tuple(kept),
            )
        )

    return tuple(results)
