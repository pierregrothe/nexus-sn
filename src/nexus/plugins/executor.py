# src/nexus/plugins/executor.py
# PluginExecutor + result models for SN plugin write operations.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Plugin execution orchestrator and result models."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Self, cast

from pydantic import BaseModel, ConfigDict, model_validator

if TYPE_CHECKING:
    from rich.console import Console

    from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol
    from nexus.plugins.diff import PromotionPlan

from nexus.plugins.dependencies import fetch_dependencies
from nexus.plugins.errors import (
    PluginImpactBlockError,
    PluginNotFoundError,
    PluginProgressError,
    PluginTimeoutError,
)
from nexus.plugins.impact import reverse_dependencies
from nexus.plugins.models import PluginInfo, PluginInventory
from nexus.plugins.progress import ProgressPoller

__all__ = ["BatchUpgradeReport", "OperationLog", "OperationResult", "PluginExecutor"]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class OperationResult(BaseModel):
    """Result of one plugin operation.

    Attributes:
        action: install, activate, upgrade, uninstall, deactivate, or
            rollback_<action>.
        plugin_id: Canonical plugin identifier.
        success: True if SN reported success.
        message: SN's status_label or our error description.
        duration_s: Wall-clock seconds.
        tracker_id: The progress tracker sys_id, "" for synthetic results.
        update_set: SN-provided update set sys_id, if any.
        rollback_version: Version SN would roll back to, if reported.
    """

    model_config = _FROZEN

    action: Literal[
        "install",
        "activate",
        "upgrade",
        "uninstall",
        "deactivate",
        "rollback_install",
        "rollback_activate",
        "rollback_upgrade",
    ]
    plugin_id: str
    success: bool
    message: str
    duration_s: float
    tracker_id: str
    update_set: str | None
    rollback_version: str | None


class OperationLog(BaseModel):
    """Ordered sequence of OperationResults from an apply_plan call.

    Attributes:
        results: Operations in execution order. Rollback entries appear
            after the failing forward-step in reverse order.
    """

    model_config = _FROZEN

    results: tuple[OperationResult, ...]

    @property
    def success_count(self) -> int:
        """Number of results with success=True."""
        return sum(1 for r in self.results if r.success)

    @property
    def failure_count(self) -> int:
        """Number of results with success=False."""
        return sum(1 for r in self.results if not r.success)


class BatchUpgradeReport(BaseModel):
    """Aggregate result of PluginExecutor.batch_upgrade.

    Attributes:
        results: One OperationResult per attempted plugin, in execution order.
        families: Family names used to filter targets, echoed back on the report.
            Empty tuple when no filter was applied.
        target_count: Number of plugins attempted (==len(results)).
        succeeded: Number of results with success=True.
        failed: Number of results with success=False.

    Construction enforces ``target_count == len(results)`` and
    ``succeeded + failed == target_count`` -- callers cannot build an
    incoherent report.
    """

    model_config = _FROZEN

    results: tuple[OperationResult, ...]
    families: tuple[str, ...]
    target_count: int
    succeeded: int
    failed: int

    @model_validator(mode="after")
    def _check_counts_coherent(self) -> Self:
        """Reject reports whose counts do not match the ``results`` tuple."""
        if self.target_count != len(self.results):
            raise ValueError(
                f"target_count ({self.target_count}) != len(results) ({len(self.results)})"
            )
        actual_succeeded = sum(1 for r in self.results if r.success)
        if self.succeeded != actual_succeeded:
            raise ValueError(f"succeeded ({self.succeeded}) != actual ({actual_succeeded})")
        if self.succeeded + self.failed != self.target_count:
            raise ValueError(
                f"succeeded + failed ({self.succeeded + self.failed}) "
                f"!= target_count ({self.target_count})"
            )
        return self

    @property
    def exit_code(self) -> int:
        """0 when all succeeded (including empty target -- idempotent), 1 when any failed."""
        return 0 if self.failed == 0 else 1


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
        action: Literal[
            "install",
            "activate",
            "upgrade",
            "deactivate",
            "uninstall",
            "rollback_install",
            "rollback_activate",
            "rollback_upgrade",
        ],
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
        tracker_id = str(raw.get("trackerId", ""))
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            err_msg = getattr(exc, "error_message", "") or str(exc)
            return OperationResult(
                action="install",
                plugin_id=plugin_id,
                success=False,
                message=err_msg,
                duration_s=time.monotonic() - started,
                tracker_id=tracker_id,
                update_set=None,
                rollback_version=None,
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
    ) -> OperationResult:
        """Upgrade plugin_id (optionally to a specific target_version).

        Args:
            plugin_id: Canonical plugin identifier (must be in snapshot).
            target_version: Target version, or None to upgrade to latest.

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
        try:
            raw = await self._client.submit_upgrade(info.sys_id, target_version)
        except Exception as exc:
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
        tracker_id = str(raw.get("trackerId", ""))
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            err_msg = getattr(exc, "error_message", "") or str(exc)
            return OperationResult(
                action="upgrade",
                plugin_id=plugin_id,
                success=False,
                message=err_msg,
                duration_s=time.monotonic() - started,
                tracker_id=tracker_id,
                update_set=None,
                rollback_version=None,
            )
        return OperationResult(
            action="upgrade",
            plugin_id=plugin_id,
            success=True,
            message=final.status_label,
            duration_s=time.monotonic() - started,
            tracker_id=tracker_id,
            update_set=final.update_set,
            rollback_version=final.rollback_version,
        )

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

        Returns:
            BatchUpgradeReport with per-plugin OperationResult in execution order.
        """
        results: list[OperationResult] = []
        for plugin in targets:
            console.print(f"[label]upgrade {plugin.plugin_id}[/]")
            result = await self.upgrade(plugin.plugin_id, plugin.latest_version)
            results.append(result)
            if result.success:
                console.print(f"[ok]ok {plugin.plugin_id} -> {result.message}[/]")
            else:
                console.print(f"[error]fail {plugin.plugin_id}: {result.message}[/]")
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

            info = self._by_id.get(op.plugin_id)
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
                    raw = await self._client.submit_uninstall(info.sys_id)
                elif op.action == "activate":
                    raw = await self._client.submit_deactivate(info.sys_id)
                else:  # upgrade
                    raw = await self._client.submit_upgrade(info.sys_id, op.rollback_version)
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
            poller = ProgressPoller(self._client)
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
