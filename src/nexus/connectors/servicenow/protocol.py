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
