# src/nexus/capture/scope.py
# Discovers application scopes on a ServiceNow instance.
# Author: Pierre Grothe
# Date: 2026-05-09

"""ScopeDiscoverer: queries sys_scope and counts custom records per table per scope."""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from nexus.capture.models import ScopeEntry, ScopeManifest
from nexus.capture.tables import TableGroup
from nexus.connectors.servicenow.errors import SNClientError
from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol

log = logging.getLogger(__name__)

__all__ = ["ScopeDiscoverer"]

_SCOPE_FIELDS = "sys_id,name,scope,version,vendor"
_SCOPE_PAGE = 500
_MAX_CONCURRENT_COUNTS = 20  # matches ServiceNowClient connection pool ceiling
_DESC_NAME_WIDTH = 35  # fixed truncation width keeps progress bar stable


class ScopeDiscoverer:
    """Discovers application scopes that contain custom configurations.

    Only scopes with at least one custom record in the requested table group
    are included in the manifest -- OOTB-only scopes are silently excluded.

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
        """Return scopes that have at least one custom configuration.

        All scopes are scanned concurrently bounded by _MAX_CONCURRENT_COUNTS.
        Scopes where every table count is zero are excluded from the result --
        they contain no custom configurations relevant to this table group.

        Args:
            instance_id: Registered instance profile name (used in manifest).
            table_group: Key into table_groups to count records for.
            on_progress: Optional callback (completed, total, message). Called
                after each scope is counted. total=0 while scope list is loading.

        Returns:
            ScopeManifest with one ScopeEntry per scope that has custom configs.
        """
        group = self._groups[table_group]

        if on_progress:
            on_progress(0, 0, f"Fetching scope list from {instance_id}...")

        total_scopes = await self._client.count_records("sys_scope")
        raw_scopes: list[dict[str, object]] = []
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
        sem = asyncio.Semaphore(_MAX_CONCURRENT_COUNTS)
        completed = 0

        async def _count_scope(row: dict[str, object]) -> ScopeEntry | None:
            nonlocal completed
            scope_sys_id = str(row.get("sys_id", ""))
            query = f"sys_customer_update=true^sys_scope={scope_sys_id}"
            counts_list: list[int] = await asyncio.gather(
                *[self._safe_count(spec.name, query, sem) for spec in group.tables]
            )
            completed += 1
            if on_progress:
                name = str(row.get("name", str(row.get("scope", ""))))
                label = name[:_DESC_NAME_WIDTH].ljust(_DESC_NAME_WIDTH)
                on_progress(completed, n_scopes, f"Scanned {label}")

            # Exclude scopes with no custom records in any table
            if not any(counts_list):
                return None

            counts = {spec.name: n for spec, n in zip(group.tables, counts_list, strict=True)}
            return ScopeEntry(
                sys_id=scope_sys_id,
                name=str(row.get("name", "")),
                scope=str(row.get("scope", "")),
                version=str(row.get("version", "")),
                vendor=str(row.get("vendor", "")),
                table_counts=counts,
            )

        # return_exceptions=True prevents one failing scope from cancelling all
        # others mid-flight, which would hit the client after __aexit__ closes it.
        raw_results = await asyncio.gather(
            *[_count_scope(row) for row in raw_scopes],
            return_exceptions=True,
        )
        entries: list[ScopeEntry] = []
        for r in raw_results:
            if isinstance(r, BaseException):
                log.warning("scope count failed -- skipping: %s", r)
            elif r is not None:
                entries.append(r)

        if on_progress:
            on_progress(n_scopes, n_scopes, f"Done -- {len(entries)} scopes with custom configs")

        return ScopeManifest(
            instance_id=instance_id,
            captured_at=datetime.now(UTC),
            scopes=tuple(entries),
        )

    async def _safe_count(
        self,
        table: str,
        query: str,
        sem: asyncio.Semaphore | None = None,
    ) -> int:
        """Count records, returning 0 for unavailable tables (HTTP 400/404).

        Args:
            table: Table API name.
            query: Encoded query string.
            sem: Optional semaphore to bound concurrent API calls.

        Returns:
            Record count, or 0 if the table is absent on this instance.
        """
        try:
            if sem is not None:
                async with sem:
                    return await self._client.count_records(table, query=query)
            return await self._client.count_records(table, query=query)
        except SNClientError as exc:
            if exc.status_code in (400, 404):
                log.debug("table %s unavailable on this instance -- count=0", table)
                return 0
            raise
