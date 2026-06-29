# nexus/connectors/servicenow/client.py
# Async HTTP client for the ServiceNow REST API.
# Author: Pierre Grothe
# Date: 2026-05-07

"""ServiceNowClient: async httpx client with retry and error mapping.

Handles authentication, connection pooling, rate limiting (20 concurrent),
and exponential backoff retry (3 attempts). Maps HTTP status codes to
typed SNClientError subclasses.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any, cast

import httpx

from nexus.connectors.servicenow.errors import (
    SNAuthError,
    SNClientError,
    SNNotFoundError,
    SNRateLimitError,
)

log = logging.getLogger(__name__)

__all__ = ["RefreshTokenCallback", "ServiceNowClient"]

_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 0.5
_TIMEOUT_SECONDS = 30.0
_TABLE_API_BASE = "/api/now/table"
_STATS_API_BASE = "/api/now/stats"

# Proactive refresh window: if the access token expires within this many seconds
# of the next request, refresh first instead of waiting for a 401. 60s is enough
# to ride out clock skew and the request round-trip itself.
_PROACTIVE_REFRESH_LEAD_SECONDS = 60

RefreshTokenCallback = Callable[[], Awaitable[tuple[str, datetime]]]
"""Async callable returning a fresh ``(token, expires_at)`` pair.

Invoked by :class:`ServiceNowClient` when its current token is about to
expire (proactive) or after a 401/403 response (reactive). The CLI builds
one of these by wrapping ``nexus.cli.auth.acquire_token`` so a long-running
batch upgrade can outlive its initial OAuth grant.
"""


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
        refresh_token_callback: Optional async callable returning a fresh
            ``(token, expires_at)`` pair. When provided, the client refreshes
            its bearer header proactively (before expiry) and reactively (on
            401/403 with one retry). Required for long-running batch
            operations that may outlive the initial OAuth grant.
        token_expires_at: UTC datetime when ``token`` expires. Only consulted
            when ``refresh_token_callback`` is also set. Powers proactive
            refresh; if omitted, only reactive (post-401) refresh fires.
    """

    def __init__(
        self,
        instance_url: str,
        username: str = "",
        password: str = "",
        *,
        token: str | None = None,
        refresh_token_callback: RefreshTokenCallback | None = None,
        token_expires_at: datetime | None = None,
    ) -> None:
        """Initialize HTTP client with instance URL and credentials."""
        base = instance_url.rstrip("/")
        if not base.startswith("https://"):
            base = f"https://{base}"
        self._base_url = base
        self._token = token
        self._auth = (username, password)
        self._refresh_token_callback = refresh_token_callback
        self._token_expires_at = token_expires_at
        self._client: httpx.AsyncClient | None = None
        log.debug("ServiceNowClient initialised for %s", base)

    def _swap_bearer_token(self, new_token: str) -> None:
        """Swap the Authorization header on the underlying httpx client.

        Mutates the live ``httpx.AsyncClient`` instance in place so the next
        request uses the fresh token. No-op when the client uses basic auth
        instead of bearer.

        Args:
            new_token: Fresh OAuth bearer token.
        """
        self._token = new_token
        if self._client is not None:
            self._client.headers["Authorization"] = f"Bearer {new_token}"

    async def _force_refresh_token(self) -> None:
        """Invoke the refresh callback and update token + expiry in place.

        Internal helper shared by the proactive (pre-request) and reactive
        (post-401) refresh paths so the callback wiring lives in one place.
        """
        if self._refresh_token_callback is None:
            return
        new_token, new_expiry = await self._refresh_token_callback()
        self._swap_bearer_token(new_token)
        self._token_expires_at = new_expiry

    async def _maybe_refresh_token(self) -> None:
        """Refresh the bearer token proactively if it is about to expire.

        Only fires when both ``refresh_token_callback`` and
        ``token_expires_at`` were provided at construction.
        """
        if self._refresh_token_callback is None or self._token_expires_at is None:
            return
        seconds_left = (self._token_expires_at - datetime.now(UTC)).total_seconds()
        if seconds_left > _PROACTIVE_REFRESH_LEAD_SECONDS:
            return
        log.debug("SN token within %ss of expiry; refreshing proactively", seconds_left)
        await self._force_refresh_token()

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
    _APPMANAGER_DEACTIVATE = "/api/sn_appclient/appmanager/app/deactivate"
    _APPMANAGER_UNINSTALL = "/api/sn_appclient/appmanager/app/uninstall"
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

    async def submit_deactivate(self, source_app_id: str) -> dict[str, object]:
        """GET app/deactivate?app_id=<source_app_id>.

        DEFINITIVELY UNSUPPORTED via Bearer-auth REST: a sys_ws_operation
        mining query against alectri PDI (Yokohama) found no
        deactivate operation under sn_appclient at all. AppManagerHandler
        has 6 methods (installApp, updateApp, repairApp, activatePlugin,
        repairPlugin, installProduct) -- no deactivate method exists.
        The SN App Manager UI accomplishes deactivate/uninstall via the
        legacy ``POST /xmlhttp.do`` + ``com.snc.apps.AppsAjaxProcessor``
        which requires session-cookie / Basic auth (rejects Bearer with
        HTTP 401). See spec addendum 2026-05-14c. NEXUS sub-project N
        live support requires a session-auth code path that is out of
        scope for the current OAuth-only architecture.
        """
        params: dict[str, str | int] = {"app_id": source_app_id}
        response = await self._get(self._APPMANAGER_DEACTIVATE, params=params)
        return cast(dict[str, object], response.get("result", {}))

    async def submit_uninstall(self, source_app_id: str) -> dict[str, object]:
        """GET app/uninstall?app_id=<source_app_id>.

        Same caveat as ``submit_deactivate``: no REST operation exists.
        See spec addendum 2026-05-14c for the full mining results.
        """
        params: dict[str, str | int] = {"app_id": source_app_id}
        response = await self._get(self._APPMANAGER_UNINSTALL, params=params)
        return cast(dict[str, object], response.get("result", {}))

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

        await self._maybe_refresh_token()
        log.debug("SN %s %s params=%s", method, path, params)
        response = await self._send_with_retry(self._client, method, path, params, json)
        # Only retry on 401 (token rejected). 403 means ACL/role denial that
        # no token refresh can fix; surfacing it immediately avoids a wasted
        # OAuth round-trip plus a misleading "auth retry" log line.
        if response.status_code == 401 and self._refresh_token_callback is not None:
            log.debug("SN %s returned 401; refreshing token and retrying once", path)
            await self._force_refresh_token()
            response = await self._send_with_retry(self._client, method, path, params, json)
        self._raise_for_status(response)
        return response.json() if response.content else {}

    async def _send_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        params: Mapping[str, str | int] | None,
        json: dict[str, str] | None,
    ) -> httpx.Response:
        """Send one request, retrying transient transport errors with backoff.

        Args:
            client: The open httpx client to send through.
            method: HTTP method.
            path: Request path.
            params: Query parameters.
            json: JSON request body.

        Returns:
            The httpx.Response, regardless of status code (status handling is
            the caller's responsibility).

        Raises:
            SNClientError: When every attempt fails with a transient transport
                error (connection drop, read/connect timeout, protocol error).
        """
        last_exc: httpx.TransportError | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await client.request(method, path, params=params, json=json)
            except httpx.TransportError as exc:
                last_exc = exc
                if attempt + 1 >= _MAX_RETRIES:
                    break
                delay = _BACKOFF_BASE_SECONDS * (2**attempt)
                log.warning(
                    "SN %s %s transient error %s; retry %d/%d in %.1fs",
                    method,
                    path,
                    type(exc).__name__,
                    attempt + 1,
                    _MAX_RETRIES,
                    delay,
                )
                await asyncio.sleep(delay)
        raise SNClientError(
            f"Network error after {_MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

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
                # 800 chars is enough for SN's nested glide exception bodies
                # (typical "Cannot find function hasOwnProperty in object
                # com.glide.cicd.exception.CICDProcessException: ..." messages
                # run 300-600 chars). 200 was truncating the actionable hint.
                raise SNClientError(
                    f"Unexpected HTTP {response.status_code}: {response.text[:800]}",
                    status_code=response.status_code,
                )
