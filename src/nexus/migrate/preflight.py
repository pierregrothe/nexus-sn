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

`run_preflight` is pure over two already-open httpx.AsyncClient instances
(the CLI wiring in cli/migrate_wiring.py owns client construction and the
instance-registry auth-mode lookup); nothing here ever issues a
POST/PUT/PATCH/DELETE -- GET only (AC5).
"""

from __future__ import annotations

import httpx

from nexus.instances.role_probe import TableProbe, probe_table_access
from nexus.migrate.models import PreflightItemResult, PreflightReport, PreflightStatus

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


def _status_from_table_probe(status_code: int) -> PreflightStatus:
    """Map a TableProbeResult status code to PreflightStatus (AC2, exact).

    200 -> PASS; 403 -> FAIL; everything else (404, the synthetic status 0
    role_probe.probe_table_access reports for a network error, or a 5xx)
    -> UNKNOWN. Applies uniformly to every table-read probe in this module.

    Args:
        status_code: HTTP status code from a TableProbeResult.

    Returns:
        The mapped PreflightStatus.
    """
    if status_code == 200:
        return PreflightStatus.PASS
    if status_code == 403:
        return PreflightStatus.FAIL
    return PreflightStatus.UNKNOWN


async def _probe_table_item(
    client: httpx.AsyncClient,
    probe: TableProbe,
    *,
    item: str,
    instance: str,
    remediation: str,
) -> PreflightItemResult:
    """Run one role_probe.TableProbe and translate it into a PreflightItemResult.

    Args:
        client: Open httpx.AsyncClient for the instance being probed.
        probe: The TableProbe to execute via role_probe.probe_table_access.
        item: Preflight item id for the resulting row.
        instance: Which side ("old"/"new") this probe targets.
        remediation: Suggested remediation text shown in the rendered row.

    Returns:
        A PreflightItemResult with status mapped per AC2 (exact).
    """
    result = await probe_table_access(client, probe)
    return PreflightItemResult(
        item=item,
        instance=instance,
        status=_status_from_table_probe(result.status_code),
        purpose=probe.purpose,
        remediation=remediation,
        detail=result.detail or result.message,
    )


def _plugin_row_active(value: object) -> bool:
    """Return True when a v_plugin row's ``active`` field signals an active install.

    Mirrors ``nexus.plugins.scanner._is_active``'s truthy-string handling.
    Duplicated rather than imported: it is module-private in
    ``nexus.plugins.scanner`` (no public export exists) and pyright's
    ``reportPrivateUsage`` rejects a cross-module private import under this
    project's strict config -- the same established precedent
    ``nexus.migrate.capture_bridge`` documents for its own duplicated helper.

    Args:
        value: Raw ``active`` field value from a v_plugin row.

    Returns:
        True when the value spells an active install in any observed form.
    """
    active_states = frozenset({"true", "1", "yes", "active", "installed", "enabled"})
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in active_states
    return False


async def _probe_cicd_plugin(client: httpx.AsyncClient, instance: str) -> PreflightItemResult:
    """Probe CICD plugin (com.glide.continuousdelivery) presence + active state.

    Issues a single scoped GET against v_plugin (the plugin-inventory table
    nexus.plugins.scanner reads), filtered to the CICD plugin id -- the
    "existing plugin-inventory read" AC1 calls for, without pulling in
    PluginScanner.scan()'s concurrent sys_store_app/appmanager fan-out
    (the appmanager leg issues a POST, which would violate AC5's GET-only
    charter).

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
        rows = response.json().get("result", [])
    except ValueError:
        return PreflightItemResult(
            item=_ITEM_CICD_PLUGIN,
            instance=instance,
            status=PreflightStatus.UNKNOWN,
            purpose=purpose,
            remediation=remediation,
            detail="malformed JSON response from v_plugin",
        )
    if not rows:
        return PreflightItemResult(
            item=_ITEM_CICD_PLUGIN,
            instance=instance,
            status=PreflightStatus.FAIL,
            purpose=purpose,
            remediation=remediation,
            detail=f"{_CICD_PLUGIN_ID} not found in v_plugin",
        )
    active = _plugin_row_active(rows[0].get("active"))
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
            )
        )
        results.append(
            await _probe_table_item(
                client,
                _APP_REPO_PROBE,
                item=_ITEM_APP_REPO,
                instance=instance,
                remediation="Grant App Repository publish entitlement (admin or app_creator)",
            )
        )
        results.append(_auth_mode_result(instance, auth_mode))
    items = tuple(sorted(results, key=lambda r: (r.instance, r.item)))
    return PreflightReport(items=items)
