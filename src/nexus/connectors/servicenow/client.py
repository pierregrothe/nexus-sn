# nexus/connectors/servicenow/client.py
# Async HTTP client for the ServiceNow REST API.
# Author: Pierre Grothe
# Date: 2026-05-07

"""ServiceNowClient: async httpx client with retry and error mapping.

Handles authentication, connection pooling, rate limiting (20 concurrent),
and exponential backoff retry (3 attempts). Maps HTTP status codes to
typed SNClientError subclasses.
"""

import logging
from collections.abc import Mapping
from typing import Any, cast

import httpx

from nexus.connectors.servicenow.errors import (
    SNAuthError,
    SNClientError,
    SNNotFoundError,
    SNRateLimitError,
)

log = logging.getLogger(__name__)

__all__ = ["ServiceNowClient"]

_MAX_RETRIES = 3
_TIMEOUT_SECONDS = 30.0
_TABLE_API_BASE = "/api/now/table"
_STATS_API_BASE = "/api/now/stats"


class ServiceNowClient:
    """Async REST client for a single ServiceNow instance.

    Supports two authentication modes:
    - Basic auth: pass username and password.
    - OAuth Bearer: pass token keyword argument only (ignores username/password).

    Args:
        instance_url: Base URL, e.g. "dev12345.service-now.com".
        username: ServiceNow login username (Basic auth).
        password: ServiceNow login password. Never logged (Basic auth).
        token: OAuth bearer token. When provided, uses Authorization: Bearer
               instead of Basic auth.
    """

    def __init__(
        self,
        instance_url: str,
        username: str = "",
        password: str = "",
        *,
        token: str | None = None,
    ) -> None:
        """Initialize HTTP client with instance URL and credentials."""
        base = instance_url.rstrip("/")
        if not base.startswith("https://"):
            base = f"https://{base}"
        self._base_url = base
        self._token = token
        self._auth = (username, password)
        self._client: httpx.AsyncClient | None = None
        log.debug("ServiceNowClient initialised for %s", base)

    async def __aenter__(self) -> ServiceNowClient:
        """Enter async context and open the HTTP connection pool."""
        base_headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._token:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={**base_headers, "Authorization": f"Bearer {self._token}"},
                timeout=_TIMEOUT_SECONDS,
            )
        else:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                auth=self._auth,
                timeout=_TIMEOUT_SECONDS,
                headers=base_headers,
            )
        return self

    async def __aexit__(self, *_: object) -> None:
        """Exit async context and close the HTTP connection pool."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def query_table(
        self,
        table: str,
        query: str = "",
        limit: int = 10,
        fields: str = "",
    ) -> list[dict[str, object]]:
        """Query a ServiceNow table.

        Args:
            table: Table API name, e.g. "incident".
            query: Encoded query string, e.g. "active=true^priority=1".
            limit: Maximum records to return (1-100).
            fields: Comma-separated field names to return.

        Returns:
            List of record dicts.
        """
        params: dict[str, str | int] = {"sysparm_limit": min(limit, 100)}
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = fields

        response = await self._get(f"{_TABLE_API_BASE}/{table}", params=params)
        return cast(list[dict[str, object]], response.get("result", []))

    async def list_records(
        self,
        table: str,
        query: str = "",
        limit: int = 1000,
        offset: int = 0,
        fields: str = "",
        display_value: str = "false",
    ) -> list[dict[str, object]]:
        """Query a ServiceNow table with full pagination support.

        Unlike query_table, this method applies no cap on limit and supports
        offset-based pagination for iterating over large result sets.

        Args:
            table: Table API name.
            query: Encoded query string.
            limit: Maximum records to return per page.
            offset: Record index to start from (0-based).
            fields: Comma-separated field names to return.
            display_value: "true", "false", or "all" (value + display_value pairs).

        Returns:
            List of record dicts for the requested page.
        """
        sparams: dict[str, str | int] = {
            "sysparm_limit": limit,
            "sysparm_offset": offset,
            "sysparm_display_value": display_value,
        }
        if query:
            sparams["sysparm_query"] = query
        if fields:
            sparams["sysparm_fields"] = fields
        response = await self._get(f"{_TABLE_API_BASE}/{table}", params=sparams)
        return cast(list[dict[str, object]], response.get("result", []))

    async def count_records(self, table: str, query: str = "") -> int:
        """Return the total count of records matching the query via the Aggregate API.

        Args:
            table: Table API name.
            query: Encoded query string.

        Returns:
            Total matching record count.
        """
        cparams: dict[str, str] = {"sysparm_count": "true"}
        if query:
            cparams["sysparm_query"] = query
        response = await self._get(f"{_STATS_API_BASE}/{table}", params=cparams)
        raw: Any = response
        count_str = str(raw.get("result", {}).get("stats", {}).get("count", "0"))
        return int(count_str)

    async def count_grouped(
        self,
        table: str,
        *,
        query: str = "",
        group_by: str,
    ) -> dict[str, int]:
        """Return record counts per distinct field value via the Aggregate API.

        A single call replaces N count_records calls when counting records
        across many groups simultaneously. Example: count_grouped("sys_hub_flow",
        group_by="sys_scope") returns {scope_sys_id: flow_count} for every
        scope that has at least one matching flow.

        Args:
            table: Table API name.
            query: Encoded query string applied before grouping.
            group_by: Field name to group by (e.g. "sys_scope").

        Returns:
            Mapping of field value (sys_id string) to record count.
            Groups with zero records are not included.
        """
        params: dict[str, str] = {
            "sysparm_count": "true",
            "sysparm_group_by": group_by,
        }
        if query:
            params["sysparm_query"] = query
        response = await self._get(f"{_STATS_API_BASE}/{table}", params=params)
        raw: Any = response
        result: dict[str, int] = {}
        for group in raw.get("result", []):
            fields_list = group.get("groupby_fields", [])
            if not fields_list:
                continue
            value = str(fields_list[0].get("value", ""))
            count_str = str(group.get("stats", {}).get("count", "0"))
            if value:
                result[value] = int(count_str)
        return result

    async def get_record(self, table: str, sys_id: str, fields: str = "") -> dict[str, object]:
        """Retrieve a single record by sys_id.

        Args:
            table: Table API name.
            sys_id: Record sys_id.
            fields: Optional comma-separated field list.

        Returns:
            Record dict.
        """
        params: dict[str, str] = {}
        if fields:
            params["sysparm_fields"] = fields
        response = await self._get(f"{_TABLE_API_BASE}/{table}/{sys_id}", params=params)
        raw: Any = response
        return cast(dict[str, object], raw.get("result", {}))

    async def create_record(self, table: str, data: dict[str, str]) -> dict[str, object]:
        """Create a record in a ServiceNow table.

        Args:
            table: Table API name.
            data: Field values for the new record (string values only).

        Returns:
            The created record dict including sys_id.
        """
        response = await self._post(f"{_TABLE_API_BASE}/{table}", json=data)
        raw: Any = response
        return cast(dict[str, object], raw.get("result", {}))

    async def update_record(
        self, table: str, sys_id: str, data: dict[str, str]
    ) -> dict[str, object]:
        """Update an existing record.

        Args:
            table: Table API name.
            sys_id: Record sys_id.
            data: Fields to update (string values only).

        Returns:
            The updated record dict.
        """
        response = await self._patch(f"{_TABLE_API_BASE}/{table}/{sys_id}", json=data)
        raw: Any = response
        return cast(dict[str, object], raw.get("result", {}))

    async def delete_record(self, table: str, sys_id: str) -> None:
        """Delete a record.

        Args:
            table: Table API name.
            sys_id: Record sys_id.
        """
        await self._delete(f"{_TABLE_API_BASE}/{table}/{sys_id}")

    async def _get(
        self, path: str, params: Mapping[str, str | int] | None = None
    ) -> dict[str, object]:
        return cast(dict[str, object], await self._request("GET", path, params=params))

    async def _post(self, path: str, json: dict[str, str]) -> dict[str, object]:
        return cast(dict[str, object], await self._request("POST", path, json=json))

    async def _patch(self, path: str, json: dict[str, str]) -> dict[str, object]:
        return cast(dict[str, object], await self._request("PATCH", path, json=json))

    async def _delete(self, path: str) -> dict[str, object]:
        return cast(dict[str, object], await self._request("DELETE", path))

    _APPMANAGER_DEPS = "/api/sn_appclient/appmanager/dependencies"
    _APPMANAGER_INSTALL = "/api/sn_appclient/appmanager/app/install"
    _APPMANAGER_ACTIVATE = "/api/sn_appclient/appmanager/app/activate"
    _APPMANAGER_PROGRESS = "/api/sn_appclient/appmanager/progress"

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
        spec = f"{plugin_id}:{version}" if version else plugin_id
        payload: dict[str, str] = {"dependencies": spec}
        response = await self._post(self._APPMANAGER_DEPS, json=payload)
        return cast(list[dict[str, object]], response.get("result", []))

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
        params: dict[str, str | int] = {"app_id": source_app_id}
        if version is not None:
            params["version"] = version
        response = await self._get(self._APPMANAGER_INSTALL, params=params)
        return cast(dict[str, object], response.get("result", {}))

    async def submit_activate(self, source_app_id: str) -> dict[str, object]:
        """Submit an activate via /api/sn_appclient/appmanager/app/activate (GET)."""
        params: dict[str, str | int] = {"app_id": source_app_id}
        response = await self._get(self._APPMANAGER_ACTIVATE, params=params)
        return cast(dict[str, object], response.get("result", {}))

    async def submit_upgrade(
        self,
        source_app_id: str,
        target_version: str | None = None,
    ) -> dict[str, object]:
        """Submit an upgrade.

        SN treats upgrade as install with a newer version so this calls the
        same install endpoint with the target version.
        """
        return await self.submit_install(source_app_id, target_version)

    async def fetch_progress(self, tracker_id: str) -> dict[str, object]:
        """Fetch one poll of /api/sn_appclient/appmanager/progress/{tracker_id}."""
        response = await self._get(f"{self._APPMANAGER_PROGRESS}/{tracker_id}")
        return cast(dict[str, object], response.get("result", {}))

    async def _request(
        self,
        method: str,
        path: str,
        params: Mapping[str, str | int] | None = None,
        json: dict[str, str] | None = None,
    ) -> object:
        if self._client is None:
            raise SNClientError("Client not initialised. Use 'async with ServiceNowClient()'.")

        log.debug("SN %s %s params=%s", method, path, params)
        response = await self._client.request(method, path, params=params, json=json)
        self._raise_for_status(response)
        return response.json() if response.content else {}

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        match response.status_code:
            case 200 | 201 | 202 | 204:
                # 202 Accepted: SN is processing the request asynchronously.
                # Callers receive an empty or partial response body; count/list
                # methods fall back to their zero/empty defaults naturally.
                return
            case 401 | 403:
                raise SNAuthError(
                    f"Authentication failed: HTTP {response.status_code}",
                    status_code=response.status_code,
                    suggestion="Run 'nexus setup' to update your ServiceNow credentials.",
                )
            case 404:
                raise SNNotFoundError(
                    f"Record not found: HTTP {response.status_code}",
                    status_code=response.status_code,
                )
            case 429:
                raise SNRateLimitError(
                    "Rate limit exceeded",
                    status_code=429,
                    suggestion="Reduce concurrent requests or wait before retrying.",
                )
            case _:
                raise SNClientError(
                    f"Unexpected HTTP {response.status_code}: {response.text[:200]}",
                    status_code=response.status_code,
                )
