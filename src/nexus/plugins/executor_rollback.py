# src/nexus/plugins/executor_rollback.py
# Best-effort reverse-undo of completed plugin operations.
# Author: Pierre Grothe
# Date: 2026-07-04
"""Rollback helper for PluginExecutor.apply_plan.

Extracted from ``executor.py`` to keep that module under the 800-line
limit set by ADR-023. ``run_rollback`` is the whole body of what used to
be ``PluginExecutor._rollback``; the method now delegates here, passing
its ServiceNow client and inventory snapshot so the logic stays a pure
function of its inputs.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Literal

from nexus.plugins.errors import PluginProgressError, PluginTimeoutError
from nexus.plugins.executor_models import OperationResult
from nexus.plugins.progress import ProgressPoller

if TYPE_CHECKING:
    from rich.console import Console

    from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
    from nexus.plugins.models import PluginInfo

__all__ = ["run_rollback"]


async def run_rollback(
    client: ServiceNowClientProtocol,
    by_id: dict[str, PluginInfo],
    completed: list[OperationResult],
    console: Console,
) -> list[OperationResult]:
    """Reverse-undo each completed forward op. Best-effort, never aborts.

    Mapping (sub-project M's rollback path; sub-project N adds true
    uninstall/deactivate endpoints later):
      install   -> reuse submit_install with action label "rollback_install"
      activate  -> reuse submit_activate with action label "rollback_activate"
      upgrade   -> submit_upgrade with rollback_version captured from forward op,
                   action label "rollback_upgrade"

    Each rollback step is independent: a failed step is recorded as an
    unsuccessful OperationResult but does not stop subsequent rollbacks.

    Args:
        client: ServiceNow client used to submit the reverse operations.
        by_id: plugin_id -> PluginInfo snapshot map for sys_id resolution.
        completed: Successfully completed forward operations to undo, in
            forward order (will be processed in reverse).
        console: Rich console for status output.

    Returns:
        List of OperationResults for each rollback attempt, in LIFO order.
    """
    rollback_results: list[OperationResult] = []
    for op in reversed(completed):
        started = time.monotonic()
        console.print(f"[warn]rollback {op.action} {op.plugin_id}[/]")

        rb_action: Literal["rollback_install", "rollback_activate", "rollback_upgrade"]
        if op.action == "install":
            rb_action = "rollback_install"
        elif op.action == "activate":
            rb_action = "rollback_activate"
        elif op.action == "upgrade":
            rb_action = "rollback_upgrade"
        else:
            # Skip any non-forward action (defensive; shouldn't happen)
            continue

        info = by_id.get(op.plugin_id)
        if info is None:
            rollback_results.append(
                OperationResult(
                    action=rb_action,
                    plugin_id=op.plugin_id,
                    success=False,
                    message="rollback failed: plugin not in inventory",
                    duration_s=time.monotonic() - started,
                    tracker_id="",
                    update_set=None,
                    rollback_version=None,
                )
            )
            continue

        try:
            if op.action == "install":
                raw = await client.submit_uninstall(info.sys_id)
            elif op.action == "activate":
                raw = await client.submit_deactivate(info.sys_id)
            else:  # upgrade
                raw = await client.submit_upgrade(info.sys_id, op.rollback_version)
        except Exception as exc:
            rollback_results.append(
                OperationResult(
                    action=rb_action,
                    plugin_id=op.plugin_id,
                    success=False,
                    message=f"rollback failed: {exc}",
                    duration_s=time.monotonic() - started,
                    tracker_id="",
                    update_set=None,
                    rollback_version=None,
                )
            )
            continue

        tracker_id = str(raw.get("trackerId", ""))
        poller = ProgressPoller(client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            err_msg = getattr(exc, "error_message", "") or str(exc)
            rollback_results.append(
                OperationResult(
                    action=rb_action,
                    plugin_id=op.plugin_id,
                    success=False,
                    message=f"rollback failed: {err_msg}",
                    duration_s=time.monotonic() - started,
                    tracker_id=tracker_id,
                    update_set=None,
                    rollback_version=None,
                )
            )
            continue
        rollback_results.append(
            OperationResult(
                action=rb_action,
                plugin_id=op.plugin_id,
                success=True,
                message=final.status_label,
                duration_s=time.monotonic() - started,
                tracker_id=tracker_id,
                update_set=final.update_set,
                rollback_version=final.rollback_version,
            )
        )
    return rollback_results
