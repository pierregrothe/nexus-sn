# src/nexus/capture/scope.py
# Discovers application scopes on a ServiceNow instance.
# Author: Pierre Grothe
# Date: 2026-05-09

"""ScopeDiscoverer: queries sys_scope and counts custom records per table per scope."""

import logging
from datetime import UTC, datetime

from nexus.capture.models import ScopeEntry, ScopeManifest
from nexus.capture.tables import TableGroup
from nexus.connectors.servicenow.client import ServiceNowClient

log = logging.getLogger(__name__)

__all__ = ["ScopeDiscoverer"]

_SCOPE_FIELDS = "sys_id,name,scope,version,vendor"
_SCOPE_PAGE = 500


class ScopeDiscoverer:
    """Discovers application scopes and counts custom records per table.

    Args:
        client: Open ServiceNowClient for the target instance.
        table_groups: Mapping of group key to TableGroup.
    """

    def __init__(
        self,
        client: ServiceNowClient,
        table_groups: dict[str, TableGroup],
    ) -> None:
        """Initialize with an open client and the table group registry."""
        self._client = client
        self._groups = table_groups

    async def discover(self, instance_id: str, table_group: str) -> ScopeManifest:
        """Return all application scopes with custom record counts.

        Args:
            instance_id: Registered instance profile name (used in manifest).
            table_group: Key into table_groups to count records for.

        Returns:
            ScopeManifest with one ScopeEntry per discovered scope.
        """
        group = self._groups[table_group]
        raw_scopes = await self._client.list_records(
            "sys_scope",
            fields=_SCOPE_FIELDS,
            limit=_SCOPE_PAGE,
        )
        log.info("discovered %d scopes on %s", len(raw_scopes), instance_id)

        entries: list[ScopeEntry] = []
        for row in raw_scopes:
            scope_sys_id = str(row.get("sys_id", ""))
            counts: dict[str, int] = {}
            for spec in group.tables:
                query = f"sys_customer_update=true^sys_scope={scope_sys_id}"
                counts[spec.name] = await self._client.count_records(spec.name, query=query)
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

        return ScopeManifest(
            instance_id=instance_id,
            captured_at=datetime.now(UTC),
            scopes=tuple(entries),
        )
