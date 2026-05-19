# src/nexus/templates/results.py
# Per-record apply outcome models populated by ApplyEngine.
# Author: Pierre Grothe
# Date: 2026-05-19

"""AppliedAction enum + AppliedRecord -- carried inside ApplyResult.

v1 action set: REQUESTED (ApplyEngine sent the record and SN accepted
without an error response) and FAILED (HTTP non-2xx OR SN error body).
WARNED tier is intentionally deferred.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["AppliedAction", "AppliedRecord"]


class AppliedAction(StrEnum):
    """Per-record outcome classification at apply time."""

    REQUESTED = "REQUESTED"
    FAILED = "FAILED"


class AppliedRecord(BaseModel):
    """One record's apply outcome inside ApplyResult.

    Attributes:
        table: ServiceNow table the record was written to.
        name: Author-declared record name (used for human-readable logs).
        requested_sys_id: Deterministic sys_id the renderer generated,
            or None if the record's sys_id is server-generated.
        action: REQUESTED or FAILED.
        error_message: SN-side error text when action is FAILED, else None.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    table: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    requested_sys_id: str | None = None
    action: AppliedAction
    error_message: str | None = None
