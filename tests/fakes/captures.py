# tests/fakes/captures.py
# CaptureResult and ConfigRecord builders for assessment tests.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Helpers to construct real CaptureResult instances for tests.

The capture layer is shipped and tested; assessment tests need lightweight
ways to build small fixture data without re-implementing the CaptureEngine.
"""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.capture.models import CaptureResult, ConfigRecord, SnFieldValue

__all__ = [
    "make_capture_result",
    "make_config_record",
]


def make_config_record(
    *,
    sys_id: str = "r1",
    table: str = "sys_scope",
    scope_sys_id: str = "s1",
    scope_name: str = "x_app",
    fields: dict[str, SnFieldValue] | None = None,
    parent_sys_id: str | None = None,
) -> ConfigRecord:
    """Build a ConfigRecord with sensible defaults."""
    return ConfigRecord(
        sys_id=sys_id,
        table=table,
        scope_sys_id=scope_sys_id,
        scope_name=scope_name,
        captured_at=datetime.now(UTC),
        fields=fields or {},
        parent_sys_id=parent_sys_id,
    )


def make_capture_result(
    *,
    instance_id: str = "dev",
    scope_ids: tuple[str, ...] = ("s1",),
    table_group: str = "ai_automation",
    records: tuple[ConfigRecord, ...] = (),
) -> CaptureResult:
    """Build a CaptureResult with sensible defaults."""
    return CaptureResult(
        instance_id=instance_id,
        captured_at=datetime.now(UTC),
        scope_ids=scope_ids,
        table_group=table_group,
        records=records,
    )
