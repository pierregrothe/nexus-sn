# src/nexus/plugins/executor_models.py
# Frozen Pydantic models returned by PluginExecutor methods.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Result models for plugin write operations.

Extracted from ``executor.py`` to keep that module under the 800-line
limit set by ADR-023. These three frozen Pydantic models form the
public return-type surface of :class:`nexus.plugins.executor.PluginExecutor`
-- they are re-exported from ``executor.py`` so existing call sites
keep working unchanged.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

__all__ = ["BatchUpgradeReport", "OperationLog", "OperationResult"]

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
