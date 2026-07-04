# src/nexus/plugins/executor.py
# PluginExecutor + result models for SN plugin write operations.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Plugin execution orchestrator and result models."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, cast

from pydantic import ConfigDict

if TYPE_CHECKING:
    from rich.console import Console

    from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
    from nexus.plugins.diff import PromotionPlan
    from nexus.ui.components.batch_progress import BatchProgressProtocol

from nexus.plugins.dependencies import fetch_dependencies
from nexus.plugins.error_classification import (
    OFFERING_PLUGIN_FAILURE_MESSAGE as _OFFERING_PLUGIN_FAILURE_MESSAGE,
)
from nexus.plugins.error_classification import (
    is_already_installed_error as _is_already_installed_error,
)
from nexus.plugins.error_classification import (
    is_offering_plugin_error as _is_offering_plugin_error,
)
from nexus.plugins.errors import (
    PluginImpactBlockError,
    PluginNotFoundError,
    PluginProgressError,
    PluginTimeoutError,
)
from nexus.plugins.executor_models import (
    BatchUpgradeReport,
    OperationLog,
    OperationResult,
)
from nexus.plugins.executor_rollback import run_rollback
from nexus.plugins.impact import reverse_dependencies
from nexus.plugins.models import PluginInfo, PluginInventory
from nexus.plugins.progress import ProgressCallback, ProgressPoller, ProgressState

BatchPluginStartCallback = Callable[[int, PluginInfo], None]
BatchPluginCompleteCallback = Callable[[int, OperationResult], None]

__all__ = ["BatchUpgradeReport", "OperationLog", "OperationResult", "PluginExecutor"]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")

_Action = Literal[
    "install",
    "activate",
    "upgrade",
    "deactivate",
    "uninstall",
    "rollback_install",
    "rollback_activate",
    "rollback_upgrade",
]


class PluginExecutor:
    """Orchestrates plugin install / activate / upgrade against SN.

    Holds a snapshot of the plugin inventory built at construction. After
    each successful install, a targeted v_plugin row is fetched and added
    to the in-memory map so install -> activate sequences in one plan
    resolve sys_ids correctly without a full rescan.

    Args:
        client: ServiceNow client conforming to the protocol.
        inventory: Fresh PluginInventory captured before construction.
    """

    def __init__(
        self,
        client: ServiceNowClientProtocol,
        inventory: object,
    ) -> None:
        """Snapshot the inventory into a plugin_id -> PluginInfo map."""
        if not isinstance(inventory, PluginInventory):
            raise TypeError(f"inventory must be PluginInventory, got {type(inventory).__name__}")
        self._client = client
        self._by_id: dict[str, PluginInfo] = {p.plugin_id: p for p in inventory.plugins}
        # Cached synthetic inventory for impact-gate BFS. Invalidated whenever
        # _by_id changes (currently only via _refresh_one after install).
        self._cached_snapshot: PluginInventory | None = None

    def has_plugin(self, plugin_id: str) -> bool:
        """Return True if the plugin is known to this executor."""
        return plugin_id in self._by_id

    def lookup(self, plugin_id: str) -> PluginInfo:
        """Return the PluginInfo for plugin_id.

        Args:
            plugin_id: Canonical plugin identifier.

        Returns:
            The PluginInfo carried in the snapshot.

        Raises:
            PluginNotFoundError: When plugin_id is not in the snapshot.
        """
        info = self._by_id.get(plugin_id)
        if info is None:
            raise PluginNotFoundError(plugin_id)
        return info

    @staticmethod
    def _failure_result(
        action: _Action,
        plugin_id: str,
        message: str,
        started: float,
        *,
        tracker_id: str = "",
    ) -> OperationResult:
        """Build an unsuccessful OperationResult.

        Args:
            action: Operation label.
            plugin_id: Canonical plugin identifier.
            message: Error description.
            started: time.monotonic() value at the start of the operation.
            tracker_id: Progress tracker sys_id, empty string when unknown.

        Returns:
            OperationResult with success=False.
        """
        return OperationResult(
            action=action,
            plugin_id=plugin_id,
            success=False,
            message=message,
            duration_s=time.monotonic() - started,
            tracker_id=tracker_id,
            update_set=None,
            rollback_version=None,
        )

    def _classify_known_sn_error(
        self,
        action: Literal["install", "upgrade"],
        plugin_id: str,
        started: float,
        exc: Exception,
        *,
        tracker_id: str = "",
    ) -> OperationResult | None:
        """Return a typed OperationResult for known SN error patterns, else None."""
        if _is_already_installed_error(exc):
            return self._already_installed_result(action, plugin_id, started, tracker_id=tracker_id)
        if _is_offering_plugin_error(exc):
            return self._failure_result(
                action, plugin_id, _OFFERING_PLUGIN_FAILURE_MESSAGE, started, tracker_id=tracker_id
            )
        return None

    @staticmethod
    def _already_installed_result(
        action: Literal["install", "upgrade"],
        plugin_id: str,
        started: float,
        *,
        tracker_id: str = "",
    ) -> OperationResult:
        """Build a no-op success OperationResult for the already-installed path.

        SN's "Application version is currently installed" is treated as
        success (brew/apt idempotency). Message wording varies by ``action``
        so batch summaries stay readable.
        """
        suffix = " installed" if action == "install" else ""
        message = f"Already{suffix} at target version"
        return OperationResult(
            action=action,
            plugin_id=plugin_id,
            success=True,
            message=message,
            duration_s=time.monotonic() - started,
            tracker_id=tracker_id,
            update_set=None,
            rollback_version=None,
        )

    async def _check_impact_gate(
        self,
        plugin_id: str,
        *,
        force: bool,
    ) -> None:
        """Check the impact gate. Raise PluginImpactBlockError when triggered.

        Combines two signals:
        - local: reverse_dependencies(inventory, plugin_id) -- pure BFS over snapshot.
        - SN-live: fetch_dependencies(client, plugin_id, version) -- live cascade.

        Trips when force=False AND either source reports >0 entries.
        ``local_cross_scope_refs`` is fixed at 0 for sub-project N (cross-scope
        FK scan requires url+token not currently exposed on the executor).

        Args:
            plugin_id: Plugin under consideration.
            force: When True, the gate is bypassed entirely.

        Raises:
            PluginImpactBlockError: When force=False and the gate trips.
        """
        if force:
            return
        info = self.lookup(plugin_id)
        if self._cached_snapshot is None:
            self._cached_snapshot = PluginInventory(
                captured_at=datetime.now(UTC),
                sn_version="snapshot",
                plugins=tuple(self._by_id.values()),
            )
        local_rev = reverse_dependencies(self._cached_snapshot, plugin_id)
        local_rev_count = len(local_rev)
        sn_deps = await fetch_dependencies(self._client, plugin_id, info.version)
        sn_count = len(sn_deps)
        if local_rev_count == 0 and sn_count == 0:
            return
        raise PluginImpactBlockError(
            plugin_id=plugin_id,
            local_reverse_deps=local_rev_count,
            local_cross_scope_refs=0,
            sn_dependency_count=sn_count,
        )

    async def _refresh_one(self, plugin_id: str) -> None:
        """Fetch the v_plugin row for plugin_id and patch into the in-memory map.

        Used after install so the newly-installed plugin's sys_id is
        available to subsequent activate / upgrade calls in the same plan.
        Silently no-ops when v_plugin doesn't yet show the row (caller's
        next lookup will raise PluginNotFoundError, which is the right
        behaviour).
        """
        rows = await self._client.query_table(
            table="v_plugin",
            query=f"name={plugin_id}",
            limit=1,
        )
        if not rows:
            return
        row = rows[0]
        state_raw = row.get("state", "inactive")
        state = state_raw if state_raw in ("active", "inactive") else "inactive"
        self._by_id[plugin_id] = PluginInfo(
            plugin_id=plugin_id,
            name=str(row.get("name", plugin_id)),
            version=str(row.get("version", "")),
            state=cast(
                Literal["active", "inactive"], state
            ),  # pyright: ignore[reportUnnecessaryCast]
            source="servicenow",
            product_family="Unclassified",
            depends_on=(),
            sys_id=str(row.get("sys_id", "")),
            installed_at=None,
        )
        self._cached_snapshot = None

    async def install(
        self,
        plugin_id: str,
        version: str | None = None,
    ) -> OperationResult:
        """Install plugin_id (optionally pinned to a specific version).

        Translates plugin_id -> source_app_id via the snapshot inventory.
        After successful install, calls _refresh_one to add the new v_plugin
        row to the in-memory map.

        Args:
            plugin_id: Canonical plugin identifier (must be in snapshot).
            version: Target version, or None for latest.

        Returns:
            OperationResult with success/message/tracker_id/update_set/rollback_version.
        """
        started = time.monotonic()
        try:
            info = self.lookup(plugin_id)
        except PluginNotFoundError as exc:
            return OperationResult(
                action="install",
                plugin_id=plugin_id,
                success=False,
                message=str(exc),
                duration_s=time.monotonic() - started,
                tracker_id="",
                update_set=None,
                rollback_version=None,
            )
        try:
            raw = await self._client.submit_install(info.sys_id, version)
        except Exception as exc:
            classified = self._classify_known_sn_error("install", plugin_id, started, exc)
            if classified is not None:
                return classified
            return self._failure_result("install", plugin_id, str(exc), started)
        tracker_id = str(raw.get("trackerId", ""))
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            classified = self._classify_known_sn_error(
                "install", plugin_id, started, exc, tracker_id=tracker_id
            )
            if classified is not None:
                return classified
            err_msg = getattr(exc, "error_message", "") or str(exc)
            return self._failure_result(
                "install", plugin_id, err_msg, started, tracker_id=tracker_id
            )
        await self._refresh_one(plugin_id)
        return OperationResult(
            action="install",
            plugin_id=plugin_id,
            success=True,
            message=final.status_label,
            duration_s=time.monotonic() - started,
            tracker_id=tracker_id,
            update_set=final.update_set,
            rollback_version=final.rollback_version,
        )

    async def activate(self, plugin_id: str) -> OperationResult:
        """Activate plugin_id (must already be installed).

        Args:
            plugin_id: Canonical plugin identifier (must be in snapshot).

        Returns:
            OperationResult describing the outcome.
        """
        started = time.monotonic()
        try:
            info = self.lookup(plugin_id)
        except PluginNotFoundError as exc:
            return OperationResult(
                action="activate",
                plugin_id=plugin_id,
                success=False,
                message=str(exc),
                duration_s=time.monotonic() - started,
                tracker_id="",
                update_set=None,
                rollback_version=None,
            )
        try:
            raw = await self._client.submit_activate(info.sys_id)
        except Exception as exc:
            return OperationResult(
                action="activate",
                plugin_id=plugin_id,
                success=False,
                message=str(exc),
                duration_s=time.monotonic() - started,
                tracker_id="",
                update_set=None,
                rollback_version=None,
            )
        tracker_id = str(raw.get("trackerId", ""))
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            err_msg = getattr(exc, "error_message", "") or str(exc)
            return OperationResult(
                action="activate",
                plugin_id=plugin_id,
                success=False,
                message=err_msg,
                duration_s=time.monotonic() - started,
                tracker_id=tracker_id,
                update_set=None,
                rollback_version=None,
            )
        return OperationResult(
            action="activate",
            plugin_id=plugin_id,
            success=True,
            message=final.status_label,
            duration_s=time.monotonic() - started,
            tracker_id=tracker_id,
            update_set=final.update_set,
            rollback_version=final.rollback_version,
        )

    async def upgrade(
        self,
        plugin_id: str,
        target_version: str | None = None,
        *,
        on_progress: ProgressCallback | None = None,
        progress: BatchProgressProtocol | None = None,
    ) -> OperationResult:
        """Upgrade plugin_id (optionally to a specific target_version).

        Args:
            plugin_id: Canonical plugin identifier (must be in snapshot).
            target_version: Target version, or None to upgrade to latest.
            on_progress: Optional raw poll callback invoked with each
                ``ProgressState`` snapshot during SN's poll loop. Library
                callers use this for custom progress hooks.
            progress: Optional adaptive batch-progress driver. When set,
                ``start_item / update_item / finish_item`` are called and
                ``on_progress`` is ignored to prevent double-emission. The
                CLI uses this; library callers may leave it ``None``.

        Returns:
            OperationResult preserving rollback_version from SN.
        """
        started = time.monotonic()
        try:
            info = self.lookup(plugin_id)
        except PluginNotFoundError as exc:
            return OperationResult(
                action="upgrade",
                plugin_id=plugin_id,
                success=False,
                message=str(exc),
                duration_s=time.monotonic() - started,
                tracker_id="",
                update_set=None,
                rollback_version=None,
            )

        progress_task_id: int | None = None
        effective_on_progress: ProgressCallback | None
        if progress is not None:
            progress_task_id = progress.start_item(plugin_id, info.product_family)
            captured_progress = progress
            captured_task_id = progress_task_id

            def _forward(state: ProgressState) -> None:
                captured_progress.update_item(captured_task_id, state.percent_complete)

            effective_on_progress = _forward
        else:
            effective_on_progress = on_progress

        try:
            raw = await self._client.submit_upgrade(info.sys_id, target_version)
        except Exception as exc:
            classified = self._classify_known_sn_error("upgrade", plugin_id, started, exc)
            if classified is not None:
                if progress is not None and progress_task_id is not None:
                    progress.finish_item(
                        progress_task_id,
                        classified.duration_s,
                        info.product_family,
                        classified.success,
                    )
                return classified
            failure = self._failure_result("upgrade", plugin_id, str(exc), started)
            if progress is not None and progress_task_id is not None:
                progress.finish_item(
                    progress_task_id, failure.duration_s, info.product_family, False
                )
            return failure
        tracker_id = str(raw.get("trackerId", ""))
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id, on_progress=effective_on_progress)
        except Exception as exc:
            classified = self._classify_known_sn_error(
                "upgrade", plugin_id, started, exc, tracker_id=tracker_id
            )
            if classified is not None:
                if progress is not None and progress_task_id is not None:
                    progress.finish_item(
                        progress_task_id,
                        classified.duration_s,
                        info.product_family,
                        classified.success,
                    )
                return classified
            err_msg = getattr(exc, "error_message", "") or str(exc)
            failure = self._failure_result(
                "upgrade", plugin_id, err_msg, started, tracker_id=tracker_id
            )
            if progress is not None and progress_task_id is not None:
                progress.finish_item(
                    progress_task_id, failure.duration_s, info.product_family, False
                )
            return failure
        result = OperationResult(
            action="upgrade",
            plugin_id=plugin_id,
            success=True,
            message=final.status_label,
            duration_s=time.monotonic() - started,
            tracker_id=tracker_id,
            update_set=final.update_set,
            rollback_version=final.rollback_version,
        )
        if progress is not None and progress_task_id is not None:
            progress.finish_item(progress_task_id, result.duration_s, info.product_family, True)
        return result

    async def deactivate(
        self,
        plugin_id: str,
        *,
        force: bool = False,
    ) -> OperationResult:
        """Deactivate plugin_id with mandatory impact gate.

        Args:
            plugin_id: Canonical plugin identifier (must be in snapshot).
            force: When True, the impact gate is bypassed. The CLI surfaces
                this with a type-the-plugin-id second-confirm prompt.

        Returns:
            OperationResult describing the outcome.
        """
        started = time.monotonic()
        try:
            info = self.lookup(plugin_id)
        except PluginNotFoundError as exc:
            return self._failure_result("deactivate", plugin_id, str(exc), started)
        try:
            await self._check_impact_gate(plugin_id, force=force)
        except PluginImpactBlockError as exc:
            return self._failure_result("deactivate", plugin_id, str(exc), started)
        try:
            raw = await self._client.submit_deactivate(info.sys_id)
        except Exception as exc:
            return self._failure_result("deactivate", plugin_id, str(exc), started)
        tracker_id = str(raw.get("trackerId", ""))
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            err_msg = getattr(exc, "error_message", "") or str(exc)
            return self._failure_result(
                "deactivate", plugin_id, err_msg, started, tracker_id=tracker_id
            )
        return OperationResult(
            action="deactivate",
            plugin_id=plugin_id,
            success=True,
            message=final.status_label,
            duration_s=time.monotonic() - started,
            tracker_id=tracker_id,
            update_set=final.update_set,
            rollback_version=final.rollback_version,
        )

    async def uninstall(
        self,
        plugin_id: str,
        *,
        force: bool = False,
    ) -> OperationResult:
        """Uninstall plugin_id with mandatory impact gate + base-plugin refusal.

        Refuses unconditionally (no --force escape) when the target is a base
        ServiceNow plugin (source == "servicenow") because SN REST does not
        support uninstalling those.

        Args:
            plugin_id: Canonical plugin identifier (must be in snapshot).
            force: When True, the impact gate is bypassed (does NOT bypass
                the base-plugin refusal).

        Returns:
            OperationResult describing the outcome.
        """
        started = time.monotonic()
        try:
            info = self.lookup(plugin_id)
        except PluginNotFoundError as exc:
            return self._failure_result("uninstall", plugin_id, str(exc), started)
        if info.source == "servicenow":
            return self._failure_result(
                "uninstall",
                plugin_id,
                "base ServiceNow plugins cannot be uninstalled via REST",
                started,
            )
        try:
            await self._check_impact_gate(plugin_id, force=force)
        except PluginImpactBlockError as exc:
            return self._failure_result("uninstall", plugin_id, str(exc), started)
        try:
            raw = await self._client.submit_uninstall(info.sys_id)
        except Exception as exc:
            return self._failure_result("uninstall", plugin_id, str(exc), started)
        tracker_id = str(raw.get("trackerId", ""))
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            err_msg = getattr(exc, "error_message", "") or str(exc)
            return self._failure_result(
                "uninstall", plugin_id, err_msg, started, tracker_id=tracker_id
            )
        return OperationResult(
            action="uninstall",
            plugin_id=plugin_id,
            success=True,
            message=final.status_label,
            duration_s=time.monotonic() - started,
            tracker_id=tracker_id,
            update_set=final.update_set,
            rollback_version=final.rollback_version,
        )

    async def apply_plan(
        self,
        plan: PromotionPlan,
        *,
        console: Console,
    ) -> OperationLog:
        """Execute a PromotionPlan against the SN instance.

        Pre-validation: every plugin_id in ``activate`` and ``upgrade`` actions
        must be in the snapshot. ``install`` actions are NOT required to exist
        yet (install creates the inventory entry).

        Args:
            plan: PromotionPlan from project_to_promote_plan.
            console: Rich console for progress / status output.

        Returns:
            OperationLog with one OperationResult per executed action.
            On partial failure, includes rollback entries in reverse order.

        Raises:
            PluginNotFoundError: When an ``activate`` or ``upgrade`` action
                references a plugin not in the executor's snapshot.
        """
        for action in plan.actions:
            if action.action in ("activate", "upgrade") and action.plugin_id not in self._by_id:
                raise PluginNotFoundError(action.plugin_id)

        results: list[OperationResult] = []
        for action in plan.actions:
            console.print(f"[label]{action.action} {action.plugin_id}[/]")
            if action.action == "install":
                r = await self.install(action.plugin_id, action.target_version)
            elif action.action == "activate":
                r = await self.activate(action.plugin_id)
            else:
                # action.action == "upgrade"
                r = await self.upgrade(action.plugin_id, action.target_version)
            results.append(r)
            if not r.success:
                console.print(f"[error]failed: {r.message}[/]")
                rollback = await self._rollback(results[:-1], console)
                return OperationLog(results=tuple(results) + tuple(rollback))
        return OperationLog(results=tuple(results))

    async def batch_upgrade(
        self,
        targets: tuple[PluginInfo, ...],
        *,
        families: tuple[str, ...] = (),
        console: Console,
        on_plugin_start: BatchPluginStartCallback | None = None,
        on_plugin_progress: ProgressCallback | None = None,
        on_plugin_complete: BatchPluginCompleteCallback | None = None,
        progress: BatchProgressProtocol | None = None,
    ) -> BatchUpgradeReport:
        """Upgrade each target plugin sequentially. Skip-on-fail; never rolls back.

        Sequential by design -- ServiceNow allocates one progress tracker per
        app-manager operation per instance, so concurrent ``submit_upgrade``
        calls compete for the same tracker queue. Each plugin is upgraded to
        its ``latest_version`` (passed straight to ``submit_upgrade`` --
        ``None`` means "latest available"). Failures are recorded but the
        loop continues.

        Args:
            targets: Plugins to upgrade, in execution order. Already filtered
                upstream (by family, by needs-update).
            families: Family filter names, echoed onto the report for audit.
                Empty tuple when no filter was applied.
            console: Rich console for per-plugin status output.
            on_plugin_start: Optional callback invoked with ``(index, plugin)``
                immediately before each per-plugin upgrade kicks off. Used by
                the CLI to reset the inner per-plugin progress bar.
            on_plugin_progress: Optional callback forwarded into each
                per-plugin :meth:`upgrade`. Receives every SN tracker
                snapshot for the current plugin. The CLI uses it to drive
                the inner progress bar in real time.
            on_plugin_complete: Optional callback invoked with
                ``(index, result)`` after each plugin completes. Used by the
                CLI to advance the outer batch progress bar.
            progress: Optional adaptive batch-progress driver. When set,
                ``console`` output and per-item updates flow through it
                and the on_plugin_* callbacks are bypassed in favour of
                the protocol methods.

        Returns:
            BatchUpgradeReport with per-plugin OperationResult in execution order.
        """
        out = progress.console if progress is not None else console
        if progress is not None:
            progress.start_batch(len(targets))
        results: list[OperationResult] = []
        for index, plugin in enumerate(targets):
            if on_plugin_start is not None:
                on_plugin_start(index, plugin)
            if progress is None:
                out.print(f"[label]upgrade {plugin.plugin_id}[/]")
            result = await self.upgrade(
                plugin.plugin_id,
                plugin.latest_version,
                on_progress=on_plugin_progress if progress is None else None,
                progress=progress,
            )
            results.append(result)
            if progress is None:
                if result.success:
                    out.print(f"[ok]ok {plugin.plugin_id} -> {result.message}[/]")
                else:
                    out.print(f"[error]fail {plugin.plugin_id}: {result.message}[/]")
            if on_plugin_complete is not None:
                on_plugin_complete(index, result)
        succeeded = sum(1 for r in results if r.success)
        return BatchUpgradeReport(
            results=tuple(results),
            families=families,
            target_count=len(results),
            succeeded=succeeded,
            failed=len(results) - succeeded,
        )

    async def _rollback(
        self,
        completed: list[OperationResult],
        console: Console,
    ) -> list[OperationResult]:
        """Reverse-undo each completed forward op via :func:`run_rollback`.

        Best-effort, never aborts. Delegates to
        :func:`nexus.plugins.executor_rollback.run_rollback`, passing the
        executor's client and inventory snapshot.

        Args:
            completed: Successfully completed forward operations to undo, in
                forward order (will be processed in reverse).
            console: Rich console for status output.

        Returns:
            List of OperationResults for each rollback attempt, in LIFO order.
        """
        return await run_rollback(self._client, self._by_id, completed, console)
