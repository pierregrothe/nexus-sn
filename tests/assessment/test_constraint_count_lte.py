# tests/assessment/test_constraint_count_lte.py
# Tests for CountLteConstraint.evaluate.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 02 AC6, AC7: count_lte operator."""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.assessment.schemas.constraints import CountLteConstraint
from nexus.capture.models import ConfigRecord

NOW = datetime.now(UTC)


def _record(sys_id: str, **fields: str) -> ConfigRecord:
    return ConfigRecord(
        sys_id=sys_id,
        table="sys_scope",
        scope_sys_id="s1",
        scope_name="x",
        captured_at=NOW,
        fields=dict(fields),
        parent_sys_id=None,
    )


def test_count_lte_passes_when_count_at_or_under_threshold() -> None:
    constraint = CountLteConstraint(table="sys_scope", threshold=3)
    records = (_record("r1"), _record("r2"))
    result = constraint.evaluate(records)
    assert result.passed is True


def test_count_lte_fails_when_count_above_threshold() -> None:
    constraint = CountLteConstraint(table="sys_scope", threshold=1)
    records = (_record("r1"), _record("r2"))
    result = constraint.evaluate(records)
    assert result.passed is False
    assert set(result.affected_sys_ids) == {"r1", "r2"}


def test_count_lte_with_threshold_zero_passes_on_empty() -> None:
    constraint = CountLteConstraint(table="sys_scope", threshold=0)
    result = constraint.evaluate(())
    assert result.passed is True


def test_count_lte_respects_filter() -> None:
    constraint = CountLteConstraint(table="sys_scope", threshold=1, filter=(("active", "true"),))
    records = (
        _record("r1", active="true"),
        _record("r2", active="false"),
        _record("r3", active="false"),
    )
    result = constraint.evaluate(records)
    assert result.passed is True
