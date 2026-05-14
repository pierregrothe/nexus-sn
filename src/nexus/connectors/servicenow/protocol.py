# src/nexus/connectors/servicenow/protocol.py
# Structural protocol for the ServiceNow REST client.
# Author: Pierre Grothe
# Date: 2026-05-09

"""ServiceNowClientProtocol: interface satisfied by the real client and fakes."""

from typing import Protocol

__all__ = ["ServiceNowClientProtocol"]


class ServiceNowClientProtocol(Protocol):
    """Structural interface for the ServiceNow Table API client.

    Both ServiceNowClient and FakeServiceNowClient satisfy this protocol
    structurally without explicit inheritance.
    """

    async def list_records(
        self,
        table: str,
        query: str = "",
        limit: int = 1000,
        offset: int = 0,
        fields: str = "",
        display_value: str = "false",
    ) -> list[dict[str, object]]:
        """Return a page of records from a ServiceNow table."""
        ...

    async def count_records(self, table: str, query: str = "") -> int:
        """Return the total count of records matching the query."""
        ...

    async def query_table(
        self,
        table: str,
        query: str = "",
        limit: int = 10,
        fields: str = "",
    ) -> list[dict[str, object]]:
        """Query a ServiceNow table (bounded to 100 records internally)."""
        ...

    async def create_record(
        self,
        table: str,
        data: dict[str, str],
    ) -> dict[str, object]:
        """Create a record in a ServiceNow table and return it."""
        ...

    async def count_grouped(
        self,
        table: str,
        *,
        query: str = "",
        group_by: str,
    ) -> dict[str, int]:
        """Return record counts per distinct field value via the Aggregate API."""
        ...

    async def appmanager_dependencies(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> list[dict[str, object]]:
        """Pre-flight dependency cascade from sn_appclient.

        Args:
            plugin_id: Plugin scope, e.g. "sn_si".
            version: Target version, e.g. "13.9.23". None means latest.

        Returns:
            List of raw dependency entries from SN.
        """
        ...

    async def submit_install(
        self,
        source_app_id: str,
        version: str | None = None,
    ) -> dict[str, object]:
        """Submit an install via /api/sn_appclient/appmanager/app/install (GET).

        Args:
            source_app_id: SN sys_id of the app (from PluginInfo.sys_id).
            version: Target version to install.

        Returns:
            Raw result dict containing trackerId, status, links.progress.url,
            update_set, rollback_version.
        """
        ...

    async def submit_activate(self, source_app_id: str) -> dict[str, object]:
        """Submit an activate via /api/sn_appclient/appmanager/app/activate (GET)."""
        ...

    async def submit_upgrade(
        self,
        source_app_id: str,
        target_version: str | None = None,
    ) -> dict[str, object]:
        """Submit an upgrade.

        SN treats upgrade as install with a newer version so this calls the
        same install endpoint with the target version.
        """
        ...

    async def submit_deactivate(self, source_app_id: str) -> dict[str, object]:
        """Submit a deactivate via /api/sn_appclient/appmanager/app/deactivate (GET)."""
        ...

    async def submit_uninstall(self, source_app_id: str) -> dict[str, object]:
        """Submit an uninstall via /api/sn_appclient/appmanager/app/uninstall (GET)."""
        ...

    async def fetch_progress(self, tracker_id: str) -> dict[str, object]:
        """Fetch one poll of /api/sn_appclient/appmanager/progress/{tracker_id}."""
        ...
