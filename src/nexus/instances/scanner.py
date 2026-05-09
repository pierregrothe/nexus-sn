# src/nexus/instances/scanner.py
# Captures artifact inventory from a live ServiceNow instance.
# Author: Pierre Grothe
# Date: 2026-05-08
"""InstanceScanner: parallel REST calls to collect artifact snapshots."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import cast

import httpx

from nexus.instances.errors import SnapshotError
from nexus.instances.models import ArtifactRecord, InstanceSnapshot

__all__ = ["InstanceScanner"]

log = logging.getLogger(__name__)

_AI_SKILL_FIELDS = "sys_id,name,active,sys_updated_on,skill_type,sys_created_by,sys_scope"
_FLOW_FIELDS = "sys_id,name,active,sys_updated_on,accessible_from,sys_created_by,sys_scope"
_BR_FIELDS = "sys_id,name,active,sys_updated_on,table_name,when,sys_created_by,sys_scope"
_SI_FIELDS = "sys_id,name,active,sys_updated_on,api_name,client_callable,sys_created_by,sys_scope"

_EXTRA_FIELDS: dict[str, list[str]] = {
    "ai_skill": ["skill_type"],
    "sys_hub_flow": ["accessible_from"],
    "sys_script": ["table_name", "when"],
    "sys_script_include": ["api_name", "client_callable"],
}

_TABLE_CONFIG: dict[str, tuple[str, int]] = {
    "ai_skill": (_AI_SKILL_FIELDS, 1000),
    "sys_hub_flow": (_FLOW_FIELDS, 1000),
    "sys_script": (_BR_FIELDS, 2000),
    "sys_script_include": (_SI_FIELDS, 2000),
}


def _is_custom(row: dict[str, object]) -> bool:
    """Return True when the record was created outside the global system scope.

    Args:
        row: Raw SN Table API record dict.

    Returns:
        True if created by a non-system user in a non-global scope.
    """
    created_by = row.get("sys_created_by", "")
    scope = row.get("sys_scope", {})
    if isinstance(scope, dict):
        scope_map = cast(dict[str, object], scope)
        scope_value = str(scope_map.get("value", "global"))
    else:
        scope_value = str(scope or "global")
    return created_by != "system" and scope_value != "global"


def _parse_dt(value: str) -> datetime:
    """Parse a ServiceNow datetime string to a UTC-aware datetime.

    Args:
        value: Datetime string in "YYYY-MM-DD HH:MM:SS" format.

    Returns:
        UTC-aware datetime, or datetime.now(UTC) if parsing fails.
    """
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(UTC)


def _to_record(row: dict[str, object], extra_field_names: list[str]) -> ArtifactRecord:
    """Convert a raw SN Table API row to an ArtifactRecord.

    Args:
        row: Raw record dict from the SN Table API response.
        extra_field_names: Table-specific field names to collect into extra.

    Returns:
        ArtifactRecord populated from the row.
    """
    extra: dict[str, str | bool | int] = {}
    for key in extra_field_names:
        val = row.get(key)
        if isinstance(val, str | bool | int):
            extra[key] = val
    return ArtifactRecord(
        sys_id=str(row.get("sys_id", "")),
        name=str(row.get("name", "")),
        active=bool(row.get("active", False)),
        updated_on=_parse_dt(str(row.get("sys_updated_on", ""))),
        is_custom=_is_custom(row),
        extra=extra,
    )


class InstanceScanner:
    """Captures artifact inventory from a live ServiceNow instance.

    Args:
        transport: Optional async httpx transport for testing. Omit in production.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """See class docstring."""
        self._transport = transport

    async def scan(self, url: str, token: str, sn_version: str) -> InstanceSnapshot:
        """Capture a full artifact snapshot via four concurrent REST calls.

        Args:
            url: Instance base URL (e.g. https://dev12345.service-now.com).
            token: Bearer access token.
            sn_version: SN version string copied verbatim into the snapshot.

        Returns:
            InstanceSnapshot with all four artifact lists populated.

        Raises:
            SnapshotError: If any REST call returns a non-2xx status.
        """
        async with httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30.0,
            transport=self._transport,
        ) as client:
            ai_skills, flows, business_rules, script_includes = await asyncio.gather(
                self._fetch(client, "ai_skill"),
                self._fetch(client, "sys_hub_flow"),
                self._fetch(client, "sys_script"),
                self._fetch(client, "sys_script_include"),
            )

        return InstanceSnapshot(
            captured_at=datetime.now(UTC),
            sn_version=sn_version,
            ai_skills=ai_skills,
            flows=flows,
            business_rules=business_rules,
            script_includes=script_includes,
        )

    async def _fetch(self, client: httpx.AsyncClient, table: str) -> list[ArtifactRecord]:
        """Fetch one SN table and return a list of ArtifactRecords.

        Args:
            client: Configured async HTTP client.
            table: SN table name (e.g. 'ai_skill').

        Returns:
            List of ArtifactRecord parsed from the response.

        Raises:
            SnapshotError: If the response status is not 200.
        """
        fields, limit = _TABLE_CONFIG[table]
        resp = await client.get(
            f"/api/now/table/{table}",
            params={"sysparm_fields": fields, "sysparm_limit": limit},
        )
        if resp.status_code != 200:
            raise SnapshotError(table, resp.status_code)
        rows: list[dict[str, object]] = resp.json().get("result", [])
        return [_to_record(row, _EXTRA_FIELDS[table]) for row in rows]
