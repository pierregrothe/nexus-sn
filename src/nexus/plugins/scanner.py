# src/nexus/plugins/scanner.py
# Async REST scanner that builds a PluginInventory from v_plugin + sys_store_app.
# Author: Pierre Grothe
# Date: 2026-05-11
"""PluginScanner: concurrent reads of v_plugin and sys_store_app with dedup."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Literal, cast

import httpx

from nexus.plugins.errors import PluginScanError
from nexus.plugins.models import PluginInfo, PluginInventory
from nexus.plugins.product_families import product_family_for

__all__ = ["PluginScanner"]

log = logging.getLogger(__name__)

_V_PLUGIN_FIELDS = "sys_id,id,name,version,active,dependencies,installed_on"
_STORE_FIELDS = (
    "sys_id,scope,name,version,latest_version,active,vendor," "dependencies,sys_created_on"
)
_PAGE_LIMIT = 200
_SERVICENOW_VENDORS = {"ServiceNow", "Service-now.com", "servicenow"}
_CUSTOM_SCOPE_PREFIXES = ("x_", "u_")


class PluginScanner:
    """Reads v_plugin and sys_store_app concurrently and merges into one inventory.

    Args:
        transport: Optional httpx transport for tests. Omit in production.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """See class docstring."""
        self._transport = transport

    async def scan(self, url: str, token: str, sn_version: str) -> PluginInventory:
        """Capture the full plugin inventory.

        Args:
            url: Instance base URL.
            token: OAuth bearer token.
            sn_version: SN release name copied verbatim into the inventory.

        Returns:
            PluginInventory with deduped plugins from both tables.

        Raises:
            PluginScanError: When both source tables return non-200 responses.
        """
        async with httpx.AsyncClient(
            base_url=url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=30.0,
            transport=self._transport,
        ) as client:
            (v_rows, v_err), (s_rows, s_err) = await asyncio.gather(
                self._fetch(client, "v_plugin", _V_PLUGIN_FIELDS),
                self._fetch(client, "sys_store_app", _STORE_FIELDS),
            )

        if v_err is not None and s_err is not None:
            raise PluginScanError(s_err[0], s_err[1])

        by_id: dict[str, PluginInfo] = {}
        for row in v_rows:
            info = self._from_v_plugin(row)
            by_id[info.plugin_id] = info
        for row in s_rows:
            info = self._from_store(row)
            # sys_store_app wins on conflict because it carries vendor.
            by_id[info.plugin_id] = info

        return PluginInventory(
            captured_at=datetime.now(UTC),
            sn_version=sn_version,
            plugins=tuple(by_id.values()),
        )

    async def _fetch(
        self, client: httpx.AsyncClient, table: str, fields: str
    ) -> tuple[list[dict[str, object]], tuple[str, int] | None]:
        """Fetch one table; return ([], (table, status)) on non-200."""
        resp = await client.get(
            f"/api/now/table/{table}",
            params={"sysparm_fields": fields, "sysparm_limit": _PAGE_LIMIT},
        )
        if resp.status_code != 200:
            log.warning("plugin scan: %s returned HTTP %d", table, resp.status_code)
            return [], (table, resp.status_code)
        rows: list[dict[str, object]] = resp.json().get("result", [])
        return rows, None

    def _from_v_plugin(self, row: dict[str, object]) -> PluginInfo:
        """Build a PluginInfo from a v_plugin row."""
        plugin_id = str(row.get("id", ""))
        return PluginInfo(
            plugin_id=plugin_id,
            name=str(row.get("name", plugin_id)),
            version=str(row.get("version", "")),
            state="active" if _truthy(row.get("active")) else "inactive",
            source=_source_for(plugin_id, vendor=""),
            product_family=product_family_for(plugin_id).value,
            depends_on=_parse_deps(row.get("dependencies", "")),
            sys_id=str(row.get("sys_id", "")),
            installed_at=_parse_dt(row.get("installed_on", "")),
        )

    def _from_store(self, row: dict[str, object]) -> PluginInfo:
        """Build a PluginInfo from a sys_store_app row."""
        plugin_id = _scope_value(row.get("scope", ""))
        vendor = str(row.get("vendor", ""))
        return PluginInfo(
            plugin_id=plugin_id,
            name=str(row.get("name", plugin_id)),
            version=str(row.get("version", "")),
            state="active" if _truthy(row.get("active")) else "inactive",
            source=_source_for(plugin_id, vendor=vendor),
            product_family=product_family_for(plugin_id).value,
            depends_on=_parse_deps(row.get("dependencies", "")),
            sys_id=str(row.get("sys_id", "")),
            installed_at=_parse_dt(row.get("sys_created_on", "")),
            latest_version=str(row.get("latest_version", "")) or None,
        )


def _truthy(value: object) -> bool:
    """Coerce SN-style truthy values (bool or string) to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


def _scope_value(value: object) -> str:
    """sys_store_app.scope can be either a string or a {value, display_value} dict."""
    if isinstance(value, dict):
        scope_dict = cast(dict[str, object], value)
        return str(scope_dict.get("value", ""))
    return str(value)


def _source_for(plugin_id: str, vendor: str) -> Literal["servicenow", "store", "custom"]:
    """Derive source from plugin_id prefix and vendor string."""
    if plugin_id.startswith(_CUSTOM_SCOPE_PREFIXES):
        return "custom"
    if vendor and vendor not in _SERVICENOW_VENDORS:
        return "store"
    return "servicenow"


def _parse_deps(value: object) -> tuple[str, ...]:
    """Split a comma-separated dependency string into a tuple."""
    if not value:
        return ()
    return tuple(part.strip() for part in str(value).split(",") if part.strip())


def _parse_dt(value: object) -> datetime | None:
    """Parse SN timestamp 'YYYY-MM-DD HH:MM:SS' to a UTC datetime, or None."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None
