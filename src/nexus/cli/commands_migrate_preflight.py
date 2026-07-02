# src/nexus/cli/commands_migrate_preflight.py
# `nexus migrate preflight` subcommand -- sibling of commands_migrate.py.
# Author: Pierre Grothe
# Date: 2026-07-02

"""`nexus migrate preflight` -- read-only execution-precondition probe (Story 07).

Split into its own sibling module rather than added to
``commands_migrate.py`` (Story 07 file-size guard): that module was already
at ~473 of its 500-line cap, and a full wrapper + two-table rendering block
would have pushed it over. This module registers `@migrate_app.command
("preflight")` on the SAME shared ``migrate_app`` Typer instance from
``cli/apps.py`` and is imported for its decorator side effect from
``cli/__init__.py``, exactly like every other ``commands_*`` sibling
(ADR-023 pattern).

The production ``PreflightCollaborators.run`` wiring lives in THIS module
rather than ``cli/migrate_wiring.py`` -- that module is itself already at
482/500 lines, and adding client construction + auth-mode lookup there
would breach its own budget. Keeping a new command's collaborator seam and
its production wiring together in one single-purpose sibling module is the
same "extract a cohesive block" structural fix already applied to create
``migrate_wiring.py`` in the first place. The live-I/O wiring here is
``# pragma: no cover``, matching that established pattern; tests inject a
fake ``PreflightCollaborators`` (no live ServiceNow call).

``run_migrate_preflight`` never fails on PASS/FAIL/UNKNOWN probe content --
those are report rows, not exit codes (ADR-026 Decision 6: preflight is
advisory-only). It exits 1 only on a hard error: an unknown profile
(surfaced by ``acquire_token`` itself, already exit-1/no-traceback) or a
collaborator-reported client-construction failure (``SNClientError``,
mirroring ``run_plan``'s own collaborator-failure handling).
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

import httpx
import typer
from rich.console import RenderableType
from rich.text import Text

from nexus.cli.apps import migrate_app
from nexus.cli.auth import acquire_token as _acquire_token
from nexus.cli.console import err_console
from nexus.cli.console import render_context as _render_context
from nexus.cli.utils import trunc as _trunc
from nexus.connectors.servicenow.errors import SNClientError
from nexus.instances.models import InstanceMeta
from nexus.migrate.models import PreflightReport, PreflightStatus
from nexus.migrate.preflight import run_preflight
from nexus.ui import DataColumn, DataTable, Notice
from nexus.ui.render_context import RenderContext

__all__: list[str] = []


@dataclass(frozen=True, slots=True)
class PreflightCollaborators:
    """Injectable seam for `migrate preflight`.

    Attributes:
        run: Given the OLD and NEW instance profiles, probe both read-only
            and return the PreflightReport. Production wiring resolves each
            profile's bearer token + auth mode from the instance registry
            (auth mode is registry metadata, never a network call) and
            opens a short-lived httpx.AsyncClient per instance around
            ``nexus.migrate.preflight.run_preflight``.
    """

    run: Callable[[str, str], PreflightReport]


def run_migrate_preflight(
    *,
    from_profile: str,
    to_profile: str,
    render_context: RenderContext,
    collaborators: PreflightCollaborators,
) -> int:
    """Probe both instances read-only for migration execution preconditions.

    Args:
        from_profile: OLD (source) instance profile.
        to_profile: NEW (target) instance profile.
        render_context: Destination console for the rendered tables.
        collaborators: Injectable client-construction + auth-mode seam.

    Returns:
        Exit code 0 whenever the probe ran -- PASS/FAIL/UNKNOWN rows are
        report content, not exit codes. 1 only on a hard error: an unknown
        profile (already handled inside ``acquire_token`` with its own
        stderr message) or a collaborator-reported ``SNClientError``.
    """
    try:
        report = collaborators.run(from_profile, to_profile)
    except SNClientError as exc:
        err_console.print(Notice.error(f"failed to probe instances for preflight: {exc}"))
        return 1
    _render_preflight(report, from_profile, to_profile, render_context)
    return 0


def _status_style(status: PreflightStatus) -> str:
    """Map a PreflightStatus to the console theme style used for its cell.

    Args:
        status: The row's PreflightStatus.

    Returns:
        A theme style name ("ok"/"error"/"warn").
    """
    match status:
        case PreflightStatus.PASS:
            return "ok"
        case PreflightStatus.FAIL:
            return "error"
        case PreflightStatus.UNKNOWN:
            return "warn"
        case _:  # pragma: no cover -- exhaustive over PreflightStatus
            return "warn"


def _preflight_rows(report: PreflightReport, instance: str) -> list[list[RenderableType]]:
    """Build DataTable rows for one instance side, mirroring diagnose-roles' row shape.

    Args:
        report: The full PreflightReport (both instances).
        instance: Which side to filter rows to ("old"/"new").

    Returns:
        Rows in report order: item, status cell, purpose, remediation, detail.
    """
    rows: list[list[RenderableType]] = []
    for row in report.items:
        if row.instance != instance:
            continue
        status_cell = Text(row.status.value, style=_status_style(row.status))
        rows.append([row.item, status_cell, row.purpose, row.remediation, _trunc(row.detail, 60)])
    return rows


def _render_preflight(
    report: PreflightReport, from_profile: str, to_profile: str, render_context: RenderContext
) -> None:
    """Render one DataTable per instance side, mirroring `instance diagnose-roles` (AC3, AC4).

    Args:
        report: The full PreflightReport (both instances).
        from_profile: OLD (source) instance profile, for the table title.
        to_profile: NEW (target) instance profile, for the table title.
        render_context: Destination console.
    """
    for instance, profile in (("old", from_profile), ("new", to_profile)):
        render_context.console.print(
            DataTable(
                title=f"Preflight -- {profile}",
                columns=[
                    DataColumn(header="Item", width=22),
                    DataColumn(header="Status", width=10),
                    DataColumn(header="Purpose", width=42),
                    DataColumn(header="Remediation", width=42),
                    DataColumn(header="Detail", width=40),
                ],
                rows=_preflight_rows(report, instance),
            )
        )
    not_pass = [row for row in report.items if row.status is not PreflightStatus.PASS]
    if not not_pass:
        render_context.console.print(Notice.info("All preflight probes returned PASS."))
        return
    render_context.console.print(
        Notice.warn(
            f"{len(not_pass)} of {len(report.items)} preflight rows are not PASS -- "
            "review the 'Remediation' column before executing the plan."
        )
    )


def _auth_mode_for(meta: InstanceMeta) -> str:  # pragma: no cover -- live wiring helper
    """Derive the connected profile's auth mode from instance registry metadata.

    NEXUS instance registration is OAuth2-only today (``InstanceMeta.client_id``
    is always populated by the registration wizard); "basic" is the
    defensive fallback for a profile with no client_id, keeping AC1 row 4's
    semantics forward-compatible without inventing a Basic-auth
    registration path that does not exist yet.

    Args:
        meta: Instance metadata loaded from the registry.

    Returns:
        "oauth" or "basic".
    """
    return "oauth" if meta.client_id else "basic"


def _live_preflight_run(from_profile: str, to_profile: str) -> PreflightReport:  # pragma: no cover
    """Production PreflightCollaborators.run -- live, read-only, both instances.

    Args:
        from_profile: OLD (source) instance profile.
        to_profile: NEW (target) instance profile.

    Returns:
        The PreflightReport from ``nexus.migrate.preflight.run_preflight``.
    """
    _registry_old, meta_old, token_old, _exp_old = _acquire_token(from_profile)
    _registry_new, meta_new, token_new, _exp_new = _acquire_token(to_profile)
    auth_mode_old = _auth_mode_for(meta_old)
    auth_mode_new = _auth_mode_for(meta_new)

    async def _run() -> PreflightReport:
        headers_old = {"Authorization": f"Bearer {token_old}", "Accept": "application/json"}
        headers_new = {"Authorization": f"Bearer {token_new}", "Accept": "application/json"}
        async with (
            httpx.AsyncClient(base_url=meta_old.url, headers=headers_old, timeout=30.0) as old,
            httpx.AsyncClient(base_url=meta_new.url, headers=headers_new, timeout=30.0) as new,
        ):
            return await run_preflight(
                old, new, auth_mode_old=auth_mode_old, auth_mode_new=auth_mode_new
            )

    return asyncio.run(_run())


def default_preflight_collaborators() -> PreflightCollaborators:  # pragma: no cover
    """Production wire-up: live clients + registry auth mode for `migrate preflight`.

    Returns:
        A PreflightCollaborators whose ``run`` probes both instances live.
    """
    return PreflightCollaborators(run=_live_preflight_run)


@migrate_app.command("preflight")
def migrate_preflight(  # pragma: no cover -- thin Typer wrapper over run_migrate_preflight
    from_profile: Annotated[str, typer.Option("--from", help="OLD instance profile")] = "",
    to_profile: Annotated[str, typer.Option("--to", help="NEW instance profile")] = "",
) -> None:
    """Probe both instances read-only for migration execution preconditions."""
    if not from_profile:
        err_console.print(Notice.error("--from is required"))
        raise typer.Exit(1)
    if not to_profile:
        err_console.print(Notice.error("--to is required"))
        raise typer.Exit(1)
    code = run_migrate_preflight(
        from_profile=from_profile,
        to_profile=to_profile,
        render_context=_render_context,
        collaborators=default_preflight_collaborators(),
    )
    raise typer.Exit(code)
