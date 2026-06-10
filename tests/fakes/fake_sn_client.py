# tests/fakes/fake_sn_client.py
# In-memory ServiceNow client fake for tests.
# Author: Pierre Grothe
# Date: 2026-05-07

"""FakeServiceNowClient: in-memory substitute for ServiceNowClient."""

import uuid
from collections.abc import Mapping
from typing import Any, cast

__all__ = ["FakeServiceNowClient"]


def _cell(row: Mapping[str, object], field: str) -> str:
    """Extract a row cell's scalar value for query matching.

    Reference cells are dicts (``{"link"|"display_value", "value"}``); take
    ``value`` -- mirrors ``nexus.schema.discoverer._cell``. Plain scalars
    return as a string. Missing keys return "".

    Args:
        row: A seeded record dict.
        field: Column name.

    Returns:
        The scalar value (sys_id or table name for references), else "".
    """
    raw = row.get(field)
    if isinstance(raw, dict):
        return str(cast("dict[str, object]", raw).get("value", ""))
    return "" if raw is None else str(raw)


def _condition_matches(row: Mapping[str, object], cond: str) -> bool:
    """Evaluate one encoded-query condition fragment against a row.

    Recognized forms (checked in this order):

    * ``fieldISNOTEMPTY``  -- true when the field has a non-empty value
    * ``field=value``      -- string equality on the extracted value
    * ``fieldINv1,v2,...`` -- membership in the comma-separated list

    Any other fragment is treated as match-all (returns True) so queries
    using unsupported operators never silently filter rows out.

    Args:
        row: A seeded record dict.
        cond: One condition fragment (no ``^`` separators).

    Returns:
        True when the row satisfies the condition (or it is unrecognized).
    """
    if cond.endswith("ISNOTEMPTY"):
        return _cell(row, cond.removesuffix("ISNOTEMPTY")) != ""
    if "=" in cond:
        field, _, value = cond.partition("=")
        return _cell(row, field) == value
    if "IN" in cond:
        field, _, csv = cond.partition("IN")
        return _cell(row, field) in csv.split(",")
    return True


def _row_matches(row: Mapping[str, object], query: str) -> bool:
    """Evaluate a minimal ServiceNow encoded query against one row.

    Supported grammar: ``^OR`` splits the query into alternatives and ``^``
    joins conditions inside an alternative (see ``_condition_matches`` for
    the condition forms). A row matches when ANY alternative has ALL of its
    conditions true. An empty query matches every row.

    Args:
        row: A seeded record dict.
        query: ServiceNow encoded query string.

    Returns:
        True when the row satisfies the query.
    """
    if not query:
        return True
    return any(
        all(_condition_matches(row, cond) for cond in alternative.split("^"))
        for alternative in query.split("^OR")
    )


class FakeServiceNowClient:
    """In-memory ServiceNow client that stores records in dicts.

    Suitable as a direct substitute for ServiceNowClient in tests.
    All CRUD operations work against an in-memory store.

    Args:
        initial_records: Optional seed data {table: [records]}.
    """

    def __init__(self, initial_records: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        for table, records in (initial_records or {}).items():
            self._tables[table] = [dict(r) for r in records]
        # (table, query) tuples recorded by list_records for test inspection.
        self.calls: list[tuple[str, str]] = []
        # Canned responses for the appmanager / progress endpoints (Task 7).
        self._dependency_responses: dict[str, list[dict[str, Any]]] = {}
        self._install_responses: list[dict[str, Any]] = []
        self._activate_responses: list[dict[str, Any]] = []
        self._upgrade_responses: list[dict[str, Any]] = []
        self._deactivate_responses: list[dict[str, Any]] = []
        self._uninstall_responses: list[dict[str, Any]] = []
        self._progress_sequences: dict[str, list[dict[str, Any]]] = {}

    async def __aenter__(self) -> FakeServiceNowClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def query_table(
        self,
        table: str,
        query: str = "",
        limit: int = 10,
        fields: str = "",
    ) -> list[dict[str, Any]]:
        """Return records from the in-memory table.

        Args:
            table: Table name.
            query: Ignored in fake -- returns all records.
            limit: Maximum records to return.
            fields: Ignored in fake -- returns all fields.

        Returns:
            List of record dicts, capped at limit.
        """
        return self._tables.get(table, [])[:limit]

    async def get_record(self, table: str, sys_id: str, fields: str = "") -> dict[str, Any]:
        """Return a single record by sys_id.

        Args:
            table: Table name.
            sys_id: Record identifier.
            fields: Ignored in fake.

        Returns:
            Record dict, or empty dict if not found.
        """
        for record in self._tables.get(table, []):
            if record.get("sys_id") == sys_id:
                return dict(record)
        return {}

    async def create_record(self, table: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a record and assign a fake sys_id.

        Args:
            table: Table name.
            data: Field values.

        Returns:
            Created record dict with sys_id.
        """
        record = dict(data)
        record.setdefault("sys_id", uuid.uuid4().hex)
        self._tables.setdefault(table, []).append(record)
        return dict(record)

    async def update_record(self, table: str, sys_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a record in place.

        Args:
            table: Table name.
            sys_id: Record identifier.
            data: Fields to update.

        Returns:
            Updated record dict.
        """
        for record in self._tables.get(table, []):
            if record.get("sys_id") == sys_id:
                record.update(data)
                return dict(record)
        return {}

    async def delete_record(self, table: str, sys_id: str) -> None:
        """Remove a record from the in-memory store.

        Args:
            table: Table name.
            sys_id: Record identifier.
        """
        if table in self._tables:
            self._tables[table] = [r for r in self._tables[table] if r.get("sys_id") != sys_id]

    def set_dependencies(self, plugin_id: str, entries: list[dict[str, Any]]) -> None:
        """Queue canned dependency entries keyed by plugin_id.

        Args:
            plugin_id: Plugin identifier.
            entries: List of dependency dicts to return.
        """
        self._dependency_responses[plugin_id] = list(entries)

    def queue_install_response(self, raw_result: dict[str, Any]) -> None:
        """Queue one install response (FIFO consumed by submit_install).

        Args:
            raw_result: Response dict to queue.
        """
        self._install_responses.append(dict(raw_result))

    def queue_activate_response(self, raw_result: dict[str, Any]) -> None:
        """Queue one activate response (FIFO).

        Args:
            raw_result: Response dict to queue.
        """
        self._activate_responses.append(dict(raw_result))

    def queue_upgrade_response(self, raw_result: dict[str, Any]) -> None:
        """Queue one upgrade response (FIFO).

        Args:
            raw_result: Response dict to queue.
        """
        self._upgrade_responses.append(dict(raw_result))

    def queue_deactivate_response(self, raw_result: dict[str, Any]) -> None:
        """Queue one deactivate response (FIFO).

        Args:
            raw_result: Response dict to queue.
        """
        self._deactivate_responses.append(dict(raw_result))

    def queue_uninstall_response(self, raw_result: dict[str, Any]) -> None:
        """Queue one uninstall response (FIFO).

        Args:
            raw_result: Response dict to queue.
        """
        self._uninstall_responses.append(dict(raw_result))

    def set_progress_sequence(self, tracker_id: str, sequence: list[dict[str, Any]]) -> None:
        """Set the sequence of polls returned for one tracker_id (FIFO).

        Args:
            tracker_id: Progress tracker identifier.
            sequence: List of progress response dicts to return in order.
        """
        self._progress_sequences[tracker_id] = list(sequence)

    async def list_records(
        self,
        table: str,
        query: str = "",
        limit: int = 1000,
        offset: int = 0,
        fields: str = "",
        display_value: str = "false",
    ) -> list[dict[str, Any]]:
        """Return a filtered page of records from the in-memory table.

        The encoded query is interpreted with a minimal grammar (see
        ``_row_matches``); unrecognized condition fragments match all rows.
        Offset/limit slicing is applied AFTER filtering, mirroring the real
        Table API. Each call appends a (table, query) tuple to ``calls``.

        Args:
            table: Table name.
            query: ServiceNow encoded query (minimal grammar; "" matches all).
            limit: Maximum records to return.
            offset: Starting record index within the filtered result.
            fields: Ignored in fake.
            display_value: Ignored in fake.

        Returns:
            List of record dicts for the requested page.
        """
        self.calls.append((table, query))
        matched = [r for r in self._tables.get(table, []) if _row_matches(r, query)]
        return matched[offset : offset + limit]

    async def count_records(self, table: str, query: str = "") -> int:
        """Return the total count of records in the table.

        Args:
            table: Table name.
            query: Ignored in fake -- counts all records.

        Returns:
            Total record count.
        """
        return len(self._tables.get(table, []))

    async def count_grouped(self, table: str, *, query: str = "", group_by: str) -> dict[str, int]:
        """Return per-group record counts by inspecting the group_by field.

        Args:
            table: Table name.
            query: Ignored in fake.
            group_by: Field name to group by.

        Returns:
            Mapping of field value to count.
        """
        result: dict[str, int] = {}
        for record in self._tables.get(table, []):
            value = str(record.get(group_by, ""))
            if value:
                result[value] = result.get(value, 0) + 1
        return result

    async def appmanager_dependencies(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return canned dependency entries for plugin_id, or empty list.

        Args:
            plugin_id: Plugin identifier.
            version: Version (ignored by fake).

        Returns:
            List of dependency dicts or empty list if none queued.
        """
        del version  # canned shape ignores version
        return list(self._dependency_responses.get(plugin_id, []))

    async def submit_install(
        self,
        source_app_id: str,
        version: str | None = None,
    ) -> dict[str, Any]:
        """Pop and return the next queued install response.

        Args:
            source_app_id: App identifier (ignored by fake).
            version: Version (ignored by fake).

        Returns:
            Response dict from the queue.

        Raises:
            RuntimeError: If no install response is queued.
        """
        del source_app_id, version
        if not self._install_responses:
            raise RuntimeError("no install response queued in FakeServiceNowClient")
        return self._install_responses.pop(0)

    async def submit_activate(self, source_app_id: str) -> dict[str, Any]:
        """Pop and return the next queued activate response.

        Args:
            source_app_id: App identifier (ignored by fake).

        Returns:
            Response dict from the queue.

        Raises:
            RuntimeError: If no activate response is queued.
        """
        del source_app_id
        if not self._activate_responses:
            raise RuntimeError("no activate response queued in FakeServiceNowClient")
        return self._activate_responses.pop(0)

    async def submit_upgrade(
        self,
        source_app_id: str,
        target_version: str | None = None,
    ) -> dict[str, Any]:
        """Pop and return the next queued upgrade response.

        Args:
            source_app_id: App identifier (ignored by fake).
            target_version: Target version (ignored by fake).

        Returns:
            Response dict from the queue.

        Raises:
            RuntimeError: If no upgrade response is queued.
        """
        del source_app_id, target_version
        if not self._upgrade_responses:
            raise RuntimeError("no upgrade response queued in FakeServiceNowClient")
        return self._upgrade_responses.pop(0)

    async def submit_deactivate(self, source_app_id: str) -> dict[str, Any]:
        """Pop and return the next queued deactivate response.

        Args:
            source_app_id: App identifier (ignored by fake).

        Returns:
            Response dict from the queue.

        Raises:
            RuntimeError: If no deactivate response is queued.
        """
        del source_app_id
        if not self._deactivate_responses:
            raise RuntimeError("no deactivate response queued in FakeServiceNowClient")
        return self._deactivate_responses.pop(0)

    async def submit_uninstall(self, source_app_id: str) -> dict[str, Any]:
        """Pop and return the next queued uninstall response.

        Args:
            source_app_id: App identifier (ignored by fake).

        Returns:
            Response dict from the queue.

        Raises:
            RuntimeError: If no uninstall response is queued.
        """
        del source_app_id
        if not self._uninstall_responses:
            raise RuntimeError("no uninstall response queued in FakeServiceNowClient")
        return self._uninstall_responses.pop(0)

    async def fetch_progress(self, tracker_id: str) -> dict[str, Any]:
        """Pop and return the next progress poll for tracker_id.

        If no more polls are queued, return an auto-success terminal poll so
        tests don't get stuck in an infinite loop.

        Args:
            tracker_id: Progress tracker identifier.

        Returns:
            Progress response dict or auto-success terminal state if empty.
        """
        seq = self._progress_sequences.get(tracker_id, [])
        if not seq:
            return {
                "status": "2",
                "status_label": "Success",
                "percent_complete": 100,
                "error": "",
                "update_set": None,
                "rollback_version": None,
                "trackerId": tracker_id,
                "status_message": "",
                "status_detail": "",
            }
        return seq.pop(0)
