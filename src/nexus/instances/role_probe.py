# src/nexus/instances/role_probe.py
# OAuth-user role probe against the SN Table API tables NEXUS consumes.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Probe Table API access for the SN tables NEXUS depends on.

Powers ``nexus instance diagnose-roles`` -- a single HEAD-like read
(``GET ?sysparm_limit=1``) per critical table, mapped to a per-row
result the CLI can render. The intent is to translate the cryptic
"plugin scan: sys_store_app returned HTTP 403" warning into an
actionable role list: which table, which role, where to grant it.

Why not infer roles from ``sys_user_has_role`` alone:
* SN admin does NOT include plugin-installed roles like
  ``app_store_pa_user_role``. Reading that table tells us what the
  user has, not what NEXUS actually needs.
* Real ACL evaluation can also depend on cross-scope visibility, OAuth
  app token scopes, and conditional ACL scripts. The only reliable
  signal is hitting the actual Table API endpoint and observing the
  status code SN returns.

The curated table list is intentionally small: only tables NEXUS
itself reads via ``ServiceNowClient`` plus a baseline identity check.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    import httpx

log = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_PROBE_TABLES",
    "TableProbe",
    "TableProbeResult",
    "probe_all",
    "probe_table_access",
]


class TableProbe(BaseModel):
    """One entry in the curated probe list.

    Attributes:
        table: SN Table API name (e.g. ``v_plugin``).
        purpose: One-line description shown to the user.
        suggested_role: Role to grant when the probe returns 403. Empty
            string when no specific role is documented; the user then
            falls back to reading the SN response body directly.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    table: str
    purpose: str
    suggested_role: str


class TableProbeResult(BaseModel):
    """Outcome of probing one Table API endpoint.

    Attributes:
        probe: The ``TableProbe`` that was executed.
        status_code: HTTP status returned by SN (200 / 401 / 403 / 404 / 5xx).
        ok: True when the probe returned a 2xx.
        message: SN error ``message`` field (when status != 200).
        detail: SN error ``detail`` field (when present). Often names
            the required role on 403 responses.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    probe: TableProbe
    status_code: int
    ok: bool
    message: str
    detail: str


DEFAULT_PROBE_TABLES: tuple[TableProbe, ...] = (
    TableProbe(
        table="sys_user",
        purpose="Baseline identity (token routes to a real user)",
        suggested_role="",
    ),
    TableProbe(
        table="sys_user_has_role",
        purpose="Show what roles the OAuth user actually has",
        suggested_role="",
    ),
    TableProbe(
        table="v_plugin",
        purpose="Plugin inventory primary source",
        suggested_role="admin",
    ),
    TableProbe(
        table="sys_plugin",
        purpose="Legacy plugin table (fallback inventory source)",
        suggested_role="admin",
    ),
    TableProbe(
        table="sys_store_app",
        purpose="Store-app catalog (vendor + latest_version)",
        suggested_role="app_store_pa_user_role",
    ),
    TableProbe(
        table="sys_scope",
        purpose="Application scope metadata (capture + plugin info)",
        suggested_role="admin",
    ),
    TableProbe(
        table="sys_app",
        purpose="Scoped application records",
        suggested_role="admin",
    ),
    TableProbe(
        table="sys_metadata",
        purpose="Record counts per scope (orphan detection + impact)",
        suggested_role="admin",
    ),
)


async def probe_table_access(client: httpx.AsyncClient, probe: TableProbe) -> TableProbeResult:
    """Issue one Table API read against ``probe.table`` with ``sysparm_limit=1``.

    Args:
        client: Open ``httpx.AsyncClient`` bound to the instance URL with
            the bearer Authorization header already set.
        probe: The probe definition (table name + metadata).

    Returns:
        A ``TableProbeResult`` carrying the HTTP status and any SN-side
        error message/detail. Network errors are reported as a
        synthetic status code 0 with the exception class name in
        ``message`` so the caller can still render a row instead of
        aborting the whole probe.
    """
    url = f"/api/now/table/{probe.table}"
    try:
        response = await client.get(url, params={"sysparm_limit": 1, "sysparm_fields": "sys_id"})
    except Exception as exc:
        return TableProbeResult(
            probe=probe,
            status_code=0,
            ok=False,
            message=exc.__class__.__name__,
            detail=str(exc)[:200],
        )
    message = ""
    detail = ""
    if response.status_code != 200:
        try:
            body = cast(dict[str, object], response.json())
        except ValueError:
            body = {}
        err = cast(dict[str, object], body.get("error", {}))
        message = str(err.get("message", ""))
        detail = str(err.get("detail", ""))
    return TableProbeResult(
        probe=probe,
        status_code=response.status_code,
        ok=response.status_code == 200,
        message=message,
        detail=detail,
    )


async def probe_all(
    client: httpx.AsyncClient,
    probes: tuple[TableProbe, ...] = DEFAULT_PROBE_TABLES,
) -> tuple[TableProbeResult, ...]:
    """Run every probe sequentially and return the result tuple.

    Sequential rather than parallel: the result set is tiny (8 calls)
    and per-table responses are independent, so concurrency would only
    obscure error attribution if SN starts rate-limiting mid-probe.

    Args:
        client: Open httpx client with bearer auth header.
        probes: Probe definitions to run; defaults to the curated set.

    Returns:
        Tuple of ``TableProbeResult`` in the same order as ``probes``.
    """
    return tuple([await probe_table_access(client, p) for p in probes])
