# src/nexus/plugins/executor.py
# PluginExecutor + result models for SN plugin write operations.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Plugin execution orchestrator and result models."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from nexus.connectors.servicenow.protocol import ServiceNowClientProtocol

from nexus.plugins.errors import (
    PluginNotFoundError,
    PluginProgressError,
    PluginTimeoutError,
)
from nexus.plugins.models import PluginInfo, PluginInventory
from nexus.plugins.progress import ProgressPoller

__all__ = ["OperationLog", "OperationResult", "PluginExecutor"]

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
            raise TypeError(
                f"inventory must be PluginInventory, got {type(inventory).__name__}"
            )
        self._client = client
        self._by_id: dict[str, PluginInfo] = {p.plugin_id: p for p in inventory.plugins}

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
            state=cast(Literal["active", "inactive"], state),  # pyright: ignore[reportUnnecessaryCast]
            source="servicenow",
            product_family="Unclassified",
            depends_on=(),
            sys_id=str(row.get("sys_id", "")),
            installed_at=None,
        )

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
                action="install", plugin_id=plugin_id, success=False,
                message=str(exc), duration_s=time.monotonic() - started,
                tracker_id="", update_set=None, rollback_version=None,
            )
        try:
            raw = await self._client.submit_install(info.sys_id, version)
        except Exception as exc:
            return OperationResult(
                action="install", plugin_id=plugin_id, success=False,
                message=str(exc), duration_s=time.monotonic() - started,
                tracker_id="", update_set=None, rollback_version=None,
            )
        tracker_id = str(raw.get("trackerId", ""))
        poller = ProgressPoller(self._client)
        try:
            final = await poller.poll(tracker_id)
        except (PluginProgressError, PluginTimeoutError) as exc:
            err_msg = getattr(exc, "error_message", str(exc))
            return OperationResult(
                action="install", plugin_id=plugin_id, success=False,
                message=err_msg, duration_s=time.monotonic() - started,
                tracker_id=tracker_id, update_set=None, rollback_version=None,
            )
        await self._refresh_one(plugin_id)
        return OperationResult(
            action="install", plugin_id=plugin_id, success=True,
            message=final.status_label, duration_s=time.monotonic() - started,
            tracker_id=tracker_id, update_set=final.update_set,
            rollback_version=final.rollback_version,
        )
