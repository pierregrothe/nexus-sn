# src/nexus/migrate/preflight.py
# Read-only probe of migration execution preconditions on both instances.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Probe execution preconditions before a migration plan is executed (Story 07).

Folds spike S1 (CICD availability probe) per the brainstorm's resolved
disposition #6: `nexus migrate preflight` probes, read-only, both
instances for CICD plugin presence, sn_cicd role grantability, App
Repository entitlement, and auth mode (AC1). Every probe degrades to
FAIL/UNKNOWN on error rather than raising (ADR-026 charter hard limit 4:
advisory-only, Must Not) -- role_probe.probe_table_access's own
network-error-as-status-0 pattern is the model every probe here follows,
and the sn_cicd-role/App-Repo probes reuse that primitive verbatim rather
than reimplementing GET + error-body parsing.

Status mapping: AC2's GWT (200 -> PASS; 403 -> FAIL; 404/other ->
UNKNOWN) is the DEFAULT, and AC1's per-item rows override it. The one
override is the sn_cicd-role item: a 403 reading sys_user_role means
the probing user cannot read the role table at all, which is zero
evidence about whether the role exists or is grantable -- so that item
maps 403 -> UNKNOWN (AC1: "a 403 is reported unknown, not fail"). The
app-repo item keeps 403 -> FAIL: there a 403 on sys_app IS the
entitlement signal. Each table probe's 403 semantics are stated
explicitly at its run_preflight call site via ``status_on_403``.

`run_preflight` is pure over two already-open httpx.AsyncClient instances
(the CLI wiring in cli/migrate_wiring.py owns client construction and the
instance-registry auth-mode lookup); nothing here ever issues a
POST/PUT/PATCH/DELETE -- GET only (AC5).
"""

from __future__ import annotations

from typing import cast

import httpx

from nexus.instances.role_probe import TableProbe, probe_table_access
from nexus.migrate.models import PreflightItemResult, PreflightReport, PreflightStatus
from nexus.plugins.scanner import is_plugin_row_active

__all__ = ["MIGRATE_PREFLIGHT_PROBES", "run_preflight"]

_ITEM_CICD_PLUGIN = "cicd-plugin"
_ITEM_SN_CICD_ROLE = "sn-cicd-role"
_ITEM_APP_REPO = "app-repo-entitlement"
_ITEM_AUTH_MODE = "auth-mode"

_CICD_PLUGIN_ID = "com.glide.continuousdelivery"

_SN_CICD_ROLE_PROBE = TableProbe(
    table="sys_user_role",
    purpose="sn_cicd.sys_ci_automation role must be grantable for a CICD-driven execution",
    suggested_role="admin",
)
_APP_REPO_PROBE = TableProbe(
    table="sys_app",
    purpose="App Repository publish fields (sys_app) must be readable for App Repo lanes",
    suggested_role="admin",
)

MIGRATE_PREFLIGHT_PROBES: tuple[TableProbe, ...] = (_SN_CICD_ROLE_PROBE, _APP_REPO_PROBE)
"""The role_probe.TableProbe definitions reused for the table-read probe items."""


# AC1 override detail for the sn_cicd-role item on 403: an unreadable role
# table is zero evidence about the role itself, so tell the user exactly what
# could not be verified and that it needs a manual check.
_SN_CICD_ROLE_403_DETAIL = (
    "probe could not read sys_user_role (HTTP 403); verify the "
    "sn_cicd.sys_ci_automation role manually on this instance"
)


def _status_from_table_probe(
    status_code: int, *, status_on_403: PreflightStatus
) -> PreflightStatus:
    """Map a TableProbeResult status code to PreflightStatus.

    AC2's default mapping (200 -> PASS; 403 -> FAIL; 404, the synthetic
    status 0 role_probe.probe_table_access reports for a network error,
    or a 5xx -> UNKNOWN), with the 403 outcome supplied per probe item so
    AC1's per-item rows can override it (sn_cicd-role: 403 -> UNKNOWN).

    Args:
        status_code: HTTP status code from a TableProbeResult.
        status_on_403: The status this probe item reports on a 403 --
            FAIL when a 403 is itself the probed signal (app-repo),
            UNKNOWN when a 403 only proves the probe could not look
            (sn_cicd-role).

    Returns:
        The mapped PreflightStatus.
    """
    if status_code == 200:
        return PreflightStatus.PASS
    if status_code == 403:
        return status_on_403
    return PreflightStatus.UNKNOWN


async def _probe_table_item(
    client: httpx.AsyncClient,
    probe: TableProbe,
    *,
    item: str,
    instance: str,
    remediation: str,
    status_on_403: PreflightStatus,
    detail_on_403: str = "",
) -> PreflightItemResult:
    """Run one role_probe.TableProbe and translate it into a PreflightItemResult.

    Args:
        client: Open httpx.AsyncClient for the instance being probed.
        probe: The TableProbe to execute via role_probe.probe_table_access.
        item: Preflight item id for the resulting row.
        instance: Which side ("old"/"new") this probe targets.
        remediation: Suggested remediation text shown in the rendered row.
        status_on_403: This item's 403 outcome (AC1 per-item override of
            AC2's default FAIL); required so every call site states its
            403 semantics explicitly.
        detail_on_403: Actionable detail prefix used when the probe
            returns 403; the SN-side detail is appended when present.
            Empty means the SN-side detail is used as-is.

    Returns:
        A PreflightItemResult with status mapped per AC2's default and
        this item's AC1 override.
    """
    result = await probe_table_access(client, probe)
    detail = result.detail or result.message
    if result.status_code == 403 and detail_on_403:
        detail = f"{detail_on_403} -- {detail}" if detail else detail_on_403
    return PreflightItemResult(
        item=item,
        instance=instance,
        status=_status_from_table_probe(result.status_code, status_on_403=status_on_403),
        purpose=probe.purpose,
        remediation=remediation,
        detail=detail,
    )


async def _probe_cicd_plugin(client: httpx.AsyncClient, instance: str) -> PreflightItemResult:
    """Probe CICD plugin (com.glide.continuousdelivery) presence + active state.

    Issues a single scoped GET against v_plugin (the plugin-inventory table
    nexus.plugins.scanner reads), filtered to the CICD plugin id -- the
    "existing plugin-inventory read" AC1 calls for, without pulling in
    PluginScanner.scan()'s concurrent sys_store_app/appmanager fan-out
    (the appmanager leg issues a POST, which would violate AC5's GET-only
    charter). The row's ``active`` flag is parsed with the scanner's
    public ``is_plugin_row_active`` so the truthy-string table exists
    exactly once.

    Args:
        client: Open httpx.AsyncClient for the instance being probed.
        instance: Which side ("old"/"new") this probe targets.

    Returns:
        PASS when the plugin row is present and active; FAIL when the
        table is readable but the plugin is absent/inactive, or on a 403;
        UNKNOWN on 404/network error/malformed response (AC2).
    """
    purpose = "CICD plugin (com.glide.continuousdelivery) must be installed and active"
    remediation = "Install and activate the CICD Spoke plugin from the SN Plugin store"
    try:
        response = await client.get(
            "/api/now/table/v_plugin",
            params={
                "sysparm_query": f"id={_CICD_PLUGIN_ID}",
                "sysparm_fields": "id,active",
                "sysparm_limit": 1,
            },
        )
    except Exception as exc:
        return PreflightItemResult(
            item=_ITEM_CICD_PLUGIN,
            instance=instance,
            status=PreflightStatus.UNKNOWN,
            purpose=purpose,
            remediation=remediation,
            detail=f"{exc.__class__.__name__}: {str(exc)[:200]}",
        )
    if response.status_code == 403:
        return PreflightItemResult(
            item=_ITEM_CICD_PLUGIN,
            instance=instance,
            status=PreflightStatus.FAIL,
            purpose=purpose,
            remediation=remediation,
            detail="HTTP 403 reading v_plugin",
        )
    if response.status_code != 200:
        return PreflightItemResult(
            item=_ITEM_CICD_PLUGIN,
            instance=instance,
            status=PreflightStatus.UNKNOWN,
            purpose=purpose,
            remediation=remediation,
            detail=f"HTTP {response.status_code} reading v_plugin",
        )
    try:
        payload: object = response.json()
    except ValueError:
        payload = None
    # A valid-but-non-object body (e.g. a bare JSON list) or a non-list
    # "result" would raise past a bare except ValueError -- both land in
    # the same UNKNOWN bucket as unparseable JSON (never-raises promise).
    result_rows = (
        cast("dict[str, object]", payload).get("result") if isinstance(payload, dict) else None
    )
    if not isinstance(result_rows, list):
        return PreflightItemResult(
            item=_ITEM_CICD_PLUGIN,
            instance=instance,
            status=PreflightStatus.UNKNOWN,
            purpose=purpose,
            remediation=remediation,
            detail="malformed JSON response from v_plugin",
        )
    rows = cast("list[object]", result_rows)
    if not rows:
        return PreflightItemResult(
            item=_ITEM_CICD_PLUGIN,
            instance=instance,
            status=PreflightStatus.FAIL,
            purpose=purpose,
            remediation=remediation,
            detail=f"{_CICD_PLUGIN_ID} not found in v_plugin",
        )
    first = rows[0]
    active = is_plugin_row_active(
        cast("dict[str, object]", first).get("active") if isinstance(first, dict) else None
    )
    return PreflightItemResult(
        item=_ITEM_CICD_PLUGIN,
        instance=instance,
        status=PreflightStatus.PASS if active else PreflightStatus.FAIL,
        purpose=purpose,
        remediation=remediation,
        detail="" if active else "plugin present but inactive",
    )


def _auth_mode_result(instance: str, auth_mode: str) -> PreflightItemResult:
    """Report the connected profile's auth mode -- always reported, never blocks (AC1 row 4).

    PASS when OAuth (case-insensitive); UNKNOWN for Basic or any other
    unrecognized value. Never FAIL: an unusual auth mode is worth flagging
    for awareness, not a hard precondition failure -- other preflight items
    already surface the preconditions that actually gate execution.

    Args:
        instance: Which side ("old"/"new") this row targets.
        auth_mode: Raw auth-mode string sourced from the instance registry
            (not a network call).

    Returns:
        A PreflightItemResult carrying ``auth_mode`` verbatim in ``detail``.
    """
    is_oauth = auth_mode.strip().lower() == "oauth"
    return PreflightItemResult(
        item=_ITEM_AUTH_MODE,
        instance=instance,
        status=PreflightStatus.PASS if is_oauth else PreflightStatus.UNKNOWN,
        purpose="Connected profile's authentication mode",
        remediation="Re-register the instance with OAuth2 for CICD-driven execution",
        detail=auth_mode,
    )


async def run_preflight(
    client_old: httpx.AsyncClient,
    client_new: httpx.AsyncClient,
    *,
    auth_mode_old: str,
    auth_mode_new: str,
) -> PreflightReport:
    """Probe execution preconditions against both instances, read-only (AC1, AC4).

    Args:
        client_old: Open httpx.AsyncClient for the OLD (source) instance.
        client_new: Open httpx.AsyncClient for the NEW (target) instance.
        auth_mode_old: OLD instance's auth mode from the instance registry
            ("oauth"/"basic"/other) -- not sourced from a network call.
        auth_mode_new: NEW instance's auth mode, same shape.

    Returns:
        A PreflightReport whose items cover every AC1 probe item against
        BOTH instances (AC4), sorted deterministically by (instance, item).
    """
    results: list[PreflightItemResult] = []
    sides = (("old", client_old, auth_mode_old), ("new", client_new, auth_mode_new))
    for instance, client, auth_mode in sides:
        results.append(await _probe_cicd_plugin(client, instance))
        results.append(
            await _probe_table_item(
                client,
                _SN_CICD_ROLE_PROBE,
                item=_ITEM_SN_CICD_ROLE,
                instance=instance,
                remediation="Grant sn_cicd.sys_ci_automation to the OAuth application user",
                # AC1 override: a 403 reading sys_user_role proves nothing
                # about the role's existence/grantability -- unknown, not fail.
                status_on_403=PreflightStatus.UNKNOWN,
                detail_on_403=_SN_CICD_ROLE_403_DETAIL,
            )
        )
        results.append(
            await _probe_table_item(
                client,
                _APP_REPO_PROBE,
                item=_ITEM_APP_REPO,
                instance=instance,
                remediation="Grant App Repository publish entitlement (admin or app_creator)",
                # AC1: a 403 on sys_app IS the entitlement signal -- fail.
                status_on_403=PreflightStatus.FAIL,
            )
        )
        results.append(_auth_mode_result(instance, auth_mode))
    items = tuple(sorted(results, key=lambda r: (r.instance, r.item)))
    return PreflightReport(items=items)
