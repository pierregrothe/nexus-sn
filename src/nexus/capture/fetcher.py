# src/nexus/capture/fetcher.py
# Paginates the ServiceNow Table API to capture custom configuration records.
# Author: Pierre Grothe
# Date: 2026-05-09

"""ConfigFetcher: fetches custom records per scope+table with pagination."""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from nexus.capture.models import ConfigRecord, SnRecord, SnRefField
from nexus.capture.tables import RelatedTable, TableGroup, TableSpec
from nexus.connectors.servicenow.errors import SNClientError
from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol

log = logging.getLogger(__name__)

__all__ = ["ConfigFetcher"]

_DEFAULT_PAGE_SIZE = 1000


def _row_to_record(
    row: dict[str, object],
    table: str,
    scope_sys_id: str,
    now: datetime,
    parent_sys_id: str | None,
) -> ConfigRecord:
    sys_id_raw = row.get("sys_id")
    sys_id = sys_id_raw if isinstance(sys_id_raw, str) else ""
    scope_raw = row.get("sys_scope")
    scope_name = scope_raw if isinstance(scope_raw, str) else scope_sys_id
    fields: SnRecord = {}
    for key, val in row.items():
        if isinstance(val, str):
            fields[key] = val
        elif isinstance(val, dict):
            val_d = cast(dict[str, object], val)
            v = val_d.get("value")
            dv = val_d.get("display_value")
            if isinstance(v, str) and isinstance(dv, str):
                ref: SnRefField = {"value": v, "display_value": dv}
                fields[key] = ref
    return ConfigRecord(
        sys_id=sys_id,
        table=table,
        scope_sys_id=scope_sys_id,
        scope_name=scope_name,
        captured_at=now,
        fields=fields,
        parent_sys_id=parent_sys_id,
    )


class ConfigFetcher:
    """Fetches custom records for a given scope and table group.

    All queries include sys_customer_update=true to exclude OOTB records.

    Args:
        client: Open ServiceNowClientProtocol for the source instance.
        table_groups: Mapping of group key to TableGroup.
        page_size: Records per paginated request.
    """

    def __init__(
        self,
        client: ServiceNowClientProtocol,
        table_groups: dict[str, TableGroup],
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> None:
        """Initialize with client, table registry, and pagination size."""
        self._client = client
        self._groups = table_groups
        self._page_size = page_size

    async def fetch(
        self,
        instance_id: str,
        scope_ids: list[str],
        table_group: str,
    ) -> list[ConfigRecord]:
        """Fetch all custom records for the given scopes.

        Args:
            instance_id: Instance profile name used in ConfigRecord metadata.
            scope_ids: Application scope sys_ids to capture.
            table_group: Key into the table group registry.

        Returns:
            Flat list of ConfigRecord (root records and related records).
        """
        group = self._groups[table_group]
        now = datetime.now(UTC)
        all_records: list[ConfigRecord] = []

        for scope_sys_id in scope_ids:
            for spec in group.tables:
                root_records = await self._fetch_table(spec, scope_sys_id, now)
                all_records.extend(root_records)

                for related in spec.related:
                    for root in root_records:
                        child_records = await self._fetch_related(
                            related, root.sys_id, scope_sys_id, now
                        )
                        all_records.extend(child_records)

        return all_records

    async def _fetch_table(
        self,
        spec: TableSpec,
        scope_sys_id: str,
        now: datetime,
    ) -> list[ConfigRecord]:
        query = f"sys_customer_update=true^{spec.scope_field}={scope_sys_id}"
        raw = await self._fetch_all_pages(spec.name, query)
        records = [
            _row_to_record(cast(dict[str, object], row), spec.name, scope_sys_id, now, None)
            for row in raw
        ]
        log.info("captured %d records from %s (scope=%s)", len(records), spec.name, scope_sys_id)
        return records

    async def _fetch_related(
        self,
        related: RelatedTable,
        parent_sys_id: str,
        scope_sys_id: str,
        now: datetime,
    ) -> list[ConfigRecord]:
        query = f"sys_customer_update=true^{related.join_field}={parent_sys_id}"
        raw = await self._fetch_all_pages(related.name, query)
        return [
            _row_to_record(
                cast(dict[str, object], row), related.name, scope_sys_id, now, parent_sys_id
            )
            for row in raw
        ]

    async def _fetch_all_pages(self, table: str, query: str) -> list[dict[str, Any]]:
        try:
            total = await self._client.count_records(table, query=query)
        except SNClientError as exc:
            if exc.status_code in (400, 404):
                log.warning("table %s unavailable (HTTP %s) -- skipping", table, exc.status_code)
                return []
            raise

        all_rows: list[dict[str, Any]] = []
        offset = 0
        while offset < total:
            try:
                page = await self._client.list_records(
                    table,
                    query=query,
                    limit=self._page_size,
                    offset=offset,
                    display_value="all",
                )
            except SNClientError as exc:
                if exc.status_code in (400, 404):
                    log.warning(
                        "table %s unavailable (HTTP %s) -- skipping", table, exc.status_code
                    )
                    return all_rows
                raise
            all_rows.extend(page)
            offset += self._page_size

        return all_rows
