# src/nexus/capture/scope.py
# Discovers application scopes on a ServiceNow instance.
# Author: Pierre Grothe
# Date: 2026-05-09

"""ScopeDiscoverer: queries sys_scope and counts custom records per table per scope."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from nexus.capture.models import ScopeEntry, ScopeManifest
from nexus.capture.tables import TableGroup
from nexus.connectors.servicenow.errors import SNClientError
from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol

log = logging.getLogger(__name__)

__all__ = ["ScopeDiscoverer"]

_SCOPE_FIELDS = "sys_id,name,scope,version,vendor"
_SCOPE_PAGE = 500


class ScopeDiscoverer:
    """Discovers application scopes and counts custom records per table.

    Args:
        client: Open ServiceNowClientProtocol for the target instance.
        table_groups: Mapping of group key to TableGroup.
    """

    def __init__(
        self,
        client: ServiceNowClientProtocol,
        table_groups: dict[str, TableGroup],
    ) -> None:
        """Initialize with an open client and the table group registry."""
        self._client = client
        self._groups = table_groups

    async def discover(
        self,
        instance_id: str,
        table_group: str,
        *,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> ScopeManifest:
        """Return all application scopes with custom record counts.

        Args:
            instance_id: Registered instance profile name (used in manifest).
            table_group: Key into table_groups to count records for.
            on_progress: Optional callback (completed, total, message). Called
                after each scope is counted so callers can show a progress bar.
                total=0 means indeterminate (scope list not yet known).

        Returns:
            ScopeManifest with one ScopeEntry per discovered scope.
        """
        group = self._groups[table_group]

        if on_progress:
            on_progress(0, 0, f"Fetching scope list from {instance_id}...")

        total_scopes = await self._client.count_records("sys_scope")
        raw_scopes: list[dict[str, Any]] = []
        offset = 0
        while offset < total_scopes:
            page = await self._client.list_records(
                "sys_scope",
                fields=_SCOPE_FIELDS,
                limit=_SCOPE_PAGE,
                offset=offset,
            )
            raw_scopes.extend(page)
            offset += _SCOPE_PAGE
        log.info("discovered %d scopes on %s", len(raw_scopes), instance_id)

        n_scopes = len(raw_scopes)
        entries: list[ScopeEntry] = []
        for i, row in enumerate(raw_scopes):
            scope_name = str(row.get("name", str(row.get("scope", ""))))
            if on_progress:
                on_progress(
                    i,
                    n_scopes,
                    f"Counting records in {scope_name!r} ({i + 1}/{n_scopes})",
                )
            scope_sys_id = str(row.get("sys_id", ""))
            query = f"sys_customer_update=true^sys_scope={scope_sys_id}"
            counts_list: list[int] = await asyncio.gather(
                *[self._safe_count(spec.name, query) for spec in group.tables]
            )
            counts = {spec.name: n for spec, n in zip(group.tables, counts_list, strict=True)}
            entries.append(
                ScopeEntry(
                    sys_id=scope_sys_id,
                    name=str(row.get("name", "")),
                    scope=str(row.get("scope", "")),
                    version=str(row.get("version", "")),
                    vendor=str(row.get("vendor", "")),
                    table_counts=counts,
                )
            )

        if on_progress:
            on_progress(n_scopes, n_scopes, f"Done -- {n_scopes} scopes")

        return ScopeManifest(
            instance_id=instance_id,
            captured_at=datetime.now(UTC),
            scopes=tuple(entries),
        )

    async def _safe_count(self, table: str, query: str) -> int:
        """Count records, returning 0 for unavailable tables (HTTP 400/404).

        Args:
            table: Table API name.
            query: Encoded query string.

        Returns:
            Record count, or 0 if the table is absent on this instance.
        """
        try:
            return await self._client.count_records(table, query=query)
        except SNClientError as exc:
            if exc.status_code in (400, 404):
                log.debug("table %s unavailable on this instance -- count=0", table)
                return 0
            raise
