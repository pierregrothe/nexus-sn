# src/nexus/plugins/scanner.py
# Async REST scanner that builds a PluginInventory from v_plugin + sys_store_app.
# Author: Pierre Grothe
# Date: 2026-05-11
"""PluginScanner: concurrent reads of v_plugin and sys_store_app with dedup."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Literal, cast

import httpx

from nexus.plugins.errors import PluginScanError
from nexus.plugins.impact import (
    ScopeRecordCountError,
    ScopeRecordCountPending,
    fetch_scope_counts_with_client,
)
from nexus.plugins.models import PluginInfo, PluginInventory, ScopeRecordCount
from nexus.plugins.product_families import product_family_for

__all__ = ["PluginScanner"]

log = logging.getLogger(__name__)

_V_PLUGIN_FIELDS = "sys_id,id,name,version,active,requires,dependencies,installed_on"
_STORE_FIELDS = (
    "sys_id,scope,name,version,latest_version,active,vendor," "requires,dependencies,sys_created_on"
)
_PAGE_LIMIT = 200
_MAX_PAGES = 50  # safety cap; 50 * 200 = 10,000 rows
_SERVICENOW_VENDORS = {"ServiceNow", "Service-now.com", "servicenow"}
_CUSTOM_SCOPE_PREFIXES = ("x_", "u_")

_NEXT_LINK_RE = re.compile(r'<([^>]+)>\s*;\s*rel\s*=\s*"?next"?', re.IGNORECASE)


def _parse_next_link(header: str) -> str | None:
    """Return the URL marked rel="next" in an RFC 5988 Link header, or None.

    Tolerant of whitespace and unquoted rel values. Returns the first match;
    SN responses contain at most one rel="next" entry.

    Args:
        header: Raw value of the ``Link`` response header, or ``""``.

    Returns:
        The URL inside angle brackets paired with ``rel="next"``, else None.
    """
    if not header:
        return None
    match = _NEXT_LINK_RE.search(header)
    return match.group(1) if match else None


class PluginScanner:
    """Reads v_plugin and sys_store_app concurrently and merges into one inventory.

    Args:
        transport: Optional httpx transport for tests. Omit in production.
    """

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        """See class docstring."""
        self._transport = transport

    async def scan(
        self,
        url: str,
        token: str,
        sn_version: str,
        *,
        capture_counts: bool = True,
    ) -> PluginInventory:
        """Capture the full plugin inventory.

        Args:
            url: Instance base URL.
            token: OAuth bearer token.
            sn_version: SN release name copied verbatim into the inventory.
            capture_counts: When True (default), fan out one
                ``/api/now/stats/sys_metadata`` call per plugin to
                populate ``PluginInfo.record_counts``. When False, skip
                the fan-out -- every plugin's ``record_counts`` stays at
                ``None``. Used by ``nexus instance refresh --no-counts``
                for faster refreshes when orphan detection is not needed.

        Returns:
            PluginInventory with deduped plugins from both tables. Each
            plugin's ``record_counts`` is populated via a per-scope
            aggregate-API call under a bounded concurrency cap; per-plugin
            fetch failures leave ``record_counts`` at ``None`` without
            aborting the scan.

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

            if capture_counts:
                breakdown = await _fetch_counts(client, tuple(by_id.keys()))
                by_id = {
                    pid: info.model_copy(update={"record_counts": breakdown.get(pid)})
                    for pid, info in by_id.items()
                }

        return PluginInventory(
            captured_at=datetime.now(UTC),
            sn_version=sn_version,
            plugins=tuple(by_id.values()),
        )

    async def _fetch(
        self, client: httpx.AsyncClient, table: str, fields: str
    ) -> tuple[list[dict[str, object]], tuple[str, int] | None]:
        """Fetch a Table API endpoint, walking RFC 5988 Link rel="next" headers.

        Args:
            client: Open httpx.AsyncClient bound to the instance URL.
            table: Table name (e.g. ``v_plugin``).
            fields: Comma-separated field list for ``sysparm_fields``.

        Returns:
            ``(rows, None)`` on success; ``([], (table, status))`` on the
            first non-200 response. Pagination follows the ``Link`` header
            with ``rel="next"`` until absent. A safety cap of
            ``_MAX_PAGES`` aborts runaway loops with a WARNING.
        """
        rows: list[dict[str, object]] = []
        url = f"/api/now/table/{table}"
        params: dict[str, str | int] | None = {
            "sysparm_fields": fields,
            "sysparm_limit": _PAGE_LIMIT,
        }
        for _ in range(_MAX_PAGES):
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                log.warning("plugin scan: %s returned HTTP %d", table, resp.status_code)
                return [], (table, resp.status_code)
            rows.extend(resp.json().get("result", []))
            next_url = _parse_next_link(resp.headers.get("Link", ""))
            if next_url is None:
                return rows, None
            url = next_url
            params = None
        log.warning(
            "plugin scan: %s exceeded %d pages (%d rows); truncating",
            table,
            _MAX_PAGES,
            len(rows),
        )
        return rows, None

    def _from_v_plugin(self, row: dict[str, object]) -> PluginInfo:
        """Build a PluginInfo from a v_plugin row."""
        plugin_id = str(row.get("id", ""))
        return PluginInfo(
            plugin_id=plugin_id,
            name=str(row.get("name", plugin_id)),
            version=str(row.get("version", "")),
            state="active" if _is_active(row.get("active")) else "inactive",
            source=_source_for(plugin_id, vendor=""),
            product_family=product_family_for(plugin_id).value,
            depends_on=_parse_deps(row.get("requires", "") or row.get("dependencies", "")),
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
            state="active" if _is_active(row.get("active")) else "inactive",
            source=_source_for(plugin_id, vendor=vendor),
            product_family=product_family_for(plugin_id).value,
            depends_on=_parse_deps(row.get("requires", "") or row.get("dependencies", "")),
            sys_id=str(row.get("sys_id", "")),
            installed_at=_parse_dt(row.get("sys_created_on", "")),
            latest_version=str(row.get("latest_version", "")) or None,
            vendor=vendor,
        )


_ACTIVE_STATES = frozenset({"true", "1", "yes", "active", "installed", "enabled"})


def _is_active(value: object) -> bool:
    """Return True when an SN plugin ``active`` field signals an active install.

    SN exposes ``active`` inconsistently across releases and tables:
    Zurich v_plugin returns the string ``"active"`` / ``"inactive"``;
    older releases returned ``"true"`` / ``"false"`` or booleans; some
    edge tables (sys_plugin) use ``"installed"``. This helper accepts
    all observed truthy spellings.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _ACTIVE_STATES
    return False


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


_DEFAULT_COUNTS_CONCURRENCY = 16


async def _fetch_counts(
    client: httpx.AsyncClient,
    plugin_ids: tuple[str, ...],
    *,
    max_concurrency: int = _DEFAULT_COUNTS_CONCURRENCY,
) -> dict[str, tuple[ScopeRecordCount, ...] | None]:
    """Fan out aggregate-API calls and return per-table breakdowns.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        plugin_ids: Plugins to fetch counts for.
        max_concurrency: Maximum number of in-flight stats calls.

    Returns:
        ``plugin_id -> tuple of ScopeRecordCount`` mapping. Per-plugin
        failures surface as ``None`` so the whole refresh can succeed
        with partial data.
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    pending_count = 0

    async def _one(pid: str) -> tuple[str, tuple[ScopeRecordCount, ...] | None]:
        nonlocal pending_count
        async with semaphore:
            try:
                buckets = await fetch_scope_counts_with_client(client, pid)
            except ScopeRecordCountPending:
                pending_count += 1
                log.debug("scan: count fetch pending (HTTP 202) for %s", pid)
                return pid, None
            except ScopeRecordCountError as exc:
                log.warning("scan: count fetch failed for %s -- %s", pid, exc)
                return pid, None
            return pid, buckets

    results = await asyncio.gather(*(_one(pid) for pid in plugin_ids))
    if pending_count:
        log.info(
            "scan: %d/%d plugin count fetches returned HTTP 202 (counts unavailable)",
            pending_count,
            len(plugin_ids),
        )
    return dict(results)
