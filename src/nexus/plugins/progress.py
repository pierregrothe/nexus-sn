# src/nexus/plugins/progress.py
# ProgressState model + ProgressPoller for SN plugin operation progress.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Async progress polling for plugin operations.

ProgressState is the parsed shape of one progress observation. SN returns
two different field-name shapes -- one from the install/upgrade kickoff
endpoint, one from the progress-poll endpoint -- and ``from_sn`` accepts
either.

ProgressPoller (added in Task 6) drives a Rich progress bar by polling
/api/sn_appclient/appmanager/progress/{tracker_id} until a terminal status.
"""

from typing import cast

from pydantic import BaseModel, ConfigDict

__all__ = ["ProgressState"]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")

# SN state/status enum:
#   "0"=Pending, "1"=In Progress, "2"=Success, "3"=Failed, "4"=Cancelled.
# Treat 2-4 as terminal; only "2" is success.
_TERMINAL_STATUSES = frozenset({"2", "3", "4"})
_SUCCESS_STATUSES = frozenset({"2"})


class ProgressState(BaseModel):
    """One snapshot of an SN plugin operation's progress.

    Canonical shape (normalised from either SN response variant):

    Attributes:
        status: Numeric status as a string (SN convention: 0..4).
        status_label: Human-readable status (Pending/In Progress/Success/...).
        percent_complete: 0-100 (always int, even when SN sends as string).
        error: SN error message (empty when not failed).
        tracker_id: The progress tracker sys_id.
        update_set: sys_id of the update set, if SN created one.
        rollback_version: Version SN would roll back to, if reported.
    """

    model_config = _FROZEN

    status: str
    status_label: str
    percent_complete: int
    error: str
    tracker_id: str
    update_set: str | None
    rollback_version: str | None

    @property
    def is_terminal(self) -> bool:
        """True when SN has finished (success, failed, or cancelled)."""
        return self.status in _TERMINAL_STATUSES

    @property
    def is_success(self) -> bool:
        """True when SN reported success."""
        return self.status in _SUCCESS_STATUSES

    @classmethod
    def from_sn(cls, raw: dict[str, object]) -> ProgressState:
        """Build from either SN response variant.

        - Install/upgrade kickoff: uses ``status``, ``trackerId``, int percent_complete
        - Progress poll: uses ``state``, ``sys_id``, string percent_complete

        Missing fields default appropriately (empty strings, None, 0).
        """
        # Status: prefer "status" (kickoff) then "state" (progress poll)
        status_val = raw.get("status")
        if status_val is None:
            status_val = raw.get("state", "0")
        # Tracker id: prefer "trackerId" then "sys_id"
        tracker = raw.get("trackerId")
        if tracker is None:
            tracker = raw.get("sys_id", "")
        # Percent complete: may be string or int
        pct_raw = raw.get("percent_complete", 0) or 0
        try:
            pct = int(cast(int | str, pct_raw)) if not isinstance(pct_raw, bool) else 0
        except (TypeError, ValueError):
            pct = 0
        # Status label / error: optional with sensible defaults
        label = raw.get("status_label")
        if label is None:
            label = ""
        update_set_raw = raw.get("update_set")
        rollback_raw = raw.get("rollback_version")
        return cls(
            status=str(status_val),
            status_label=str(label),
            percent_complete=pct,
            error=str(raw.get("error", "")),
            tracker_id=str(tracker),
            update_set=str(update_set_raw) if update_set_raw else None,
            rollback_version=str(rollback_raw) if rollback_raw else None,
        )
