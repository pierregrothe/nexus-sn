# tests/fakes/fake_sn_client.py
# In-memory ServiceNow client fake for tests.
# Author: Pierre Grothe
# Date: 2026-05-07

"""FakeServiceNowClient: in-memory substitute for ServiceNowClient."""

import uuid
from typing import Any

__all__ = ["FakeServiceNowClient"]


class FakeServiceNowClient:
    """In-memory ServiceNow client that stores records in dicts.

    Suitable as a direct substitute for ServiceNowClient in tests.
    All CRUD operations work against an in-memory store.

    Args:
        initial_records: Optional seed data {table: [records]}.
    """

    def __init__(
        self, initial_records: dict[str, list[dict[str, Any]]] | None = None
    ) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}
        for table, records in (initial_records or {}).items():
            self._tables[table] = [dict(r) for r in records]

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

    async def update_record(
        self, table: str, sys_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
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
            self._tables[table] = [
                r for r in self._tables[table] if r.get("sys_id") != sys_id
            ]
