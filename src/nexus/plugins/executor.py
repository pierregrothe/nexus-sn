# src/nexus/plugins/executor.py
# PluginExecutor + result models for SN plugin write operations.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Plugin execution orchestrator and result models.

This module currently exposes only the result models. ``PluginExecutor``
itself is added in Task 8 of the sub-project M implementation plan.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = ["OperationLog", "OperationResult"]

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
