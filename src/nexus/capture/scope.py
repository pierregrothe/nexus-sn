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
_SCOPE_ID_BATCH = 200  # max scope sys_ids per IN query when fetching metadata
_DESC_NAME_WIDTH = 35  # fixed truncation width keeps progress bar stable


class ScopeDiscoverer:
    """Discovers application scopes that contain custom configurations.

    Uses the Aggregate API's group_by feature to count all scopes in one
    call per table type (5 calls total regardless of scope count) instead
    of one count call per scope per table (N*5 calls). Scopes with no
    custom records in any table are excluded from the result.

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

        Algorithm:
          1. Run one count_grouped query per table type (all concurrent).
             This returns {scope_sys_id: count} for every scope that has
             records, in ~5 API calls regardless of scope count.
          2. Merge into a per-scope count dict; exclude scopes with all zeros.
          3. Fetch scope metadata (name, scope key, version, vendor) for
             only the scopes that survived the filter.
          4. Build and return ScopeManifest.

        Args:
            instance_id: Registered instance profile name (used in manifest).
            table_group: Key into table_groups to count records for.
            on_progress: Optional callback (completed, total, message). total=0
                while scanning, total=n_tables after counts are returned.

        Returns:
            ScopeManifest with one ScopeEntry per scope that has custom configs.
        """
        group = self._groups[table_group]
        n_tables = len(group.tables)

        if on_progress:
            on_progress(0, n_tables, f"Scanning {n_tables} table types on {instance_id}...")

        # --- Step 1: one grouped count per table type, all concurrent ---
        query = "sys_customer_update=true"
        count_tasks = [
            self._safe_grouped_count(spec.name, query=query, group_by="sys_scope")
            for spec in group.tables
        ]
        raw_results = await asyncio.gather(*count_tasks, return_exceptions=True)

        # --- Step 2: merge into scope_id -> {table: count} ---
        scope_counts: dict[str, dict[str, int]] = {}
        for i, (spec, result) in enumerate(zip(group.tables, raw_results, strict=True)):
            if on_progress:
                label = spec.display[:_DESC_NAME_WIDTH].ljust(_DESC_NAME_WIDTH)
                on_progress(i + 1, n_tables, f"Scanned {label}")
            if isinstance(result, BaseException):
                log.warning("count_grouped for %s failed -- skipping: %s", spec.name, result)
                continue
            for scope_sys_id, count in result.items():
                if scope_sys_id not in scope_counts:
                    scope_counts[scope_sys_id] = {s.name: 0 for s in group.tables}
                scope_counts[scope_sys_id][spec.name] = count

        n_with_configs = len(scope_counts)
        log.info(
            "%d/%d scopes have custom configs on %s",
            n_with_configs,
            len(scope_counts),
            instance_id,
        )

        if not scope_counts:
            if on_progress:
                on_progress(n_tables, n_tables, "Done -- no scopes with custom configs")
            return ScopeManifest(
                instance_id=instance_id,
                captured_at=datetime.now(UTC),
                scopes=(),
            )

        # --- Step 3: fetch scope metadata for only the relevant scopes ---
        if on_progress:
            on_progress(
                n_tables,
                n_tables,
                f"Fetching metadata for {n_with_configs} scopes...",
            )

        scope_ids = list(scope_counts.keys())
        raw_scopes: list[dict[str, object]] = []
        for i in range(0, len(scope_ids), _SCOPE_ID_BATCH):
            batch = scope_ids[i : i + _SCOPE_ID_BATCH]
            page = await self._client.list_records(
                "sys_scope",
                query=f"sys_idIN{','.join(batch)}",
                fields=_SCOPE_FIELDS,
                limit=_SCOPE_ID_BATCH,
            )
            raw_scopes.extend(page)

        # --- Step 4: build ScopeEntry for each scope ---
        entries: list[ScopeEntry] = []
        for row in raw_scopes:
            scope_sys_id = str(row.get("sys_id", ""))
            counts = scope_counts.get(scope_sys_id, {s.name: 0 for s in group.tables})
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
            on_progress(
                n_tables,
                n_tables,
                f"Done -- {len(entries)} scopes with custom configs",
            )

        return ScopeManifest(
            instance_id=instance_id,
            captured_at=datetime.now(UTC),
            scopes=tuple(entries),
        )

    async def _safe_grouped_count(
        self,
        table: str,
        *,
        query: str = "",
        group_by: str,
    ) -> dict[str, int]:
        """Grouped count returning empty dict for unavailable tables (HTTP 400/404).

        Args:
            table: Table API name.
            query: Encoded query string.
            group_by: Field name to group by.

        Returns:
            Mapping of field value to count, or {} if the table is absent.
        """
        try:
            return await self._client.count_grouped(table, query=query, group_by=group_by)
        except SNClientError as exc:
            if exc.status_code in (400, 404):
                log.debug("table %s unavailable on this instance -- skipping", table)
                return {}
            raise
