# tests/assessment/test_constraint_count_gte.py
# Tests for CountGteConstraint.evaluate.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 02 AC5, AC7: count_gte operator."""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.assessment.schemas.constraints import CountGteConstraint
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


def test_count_gte_passes_when_count_meets_threshold() -> None:
    constraint = CountGteConstraint(table="sys_scope", threshold=2)
    records = (_record("r1"), _record("r2"), _record("r3"))
    result = constraint.evaluate(records)
    assert result.passed is True


def test_count_gte_fails_when_count_below_threshold() -> None:
    constraint = CountGteConstraint(table="sys_scope", threshold=3)
    records = (_record("r1"), _record("r2"))
    result = constraint.evaluate(records)
    assert result.passed is False


def test_count_gte_with_threshold_zero_passes_on_empty() -> None:
    constraint = CountGteConstraint(table="sys_scope", threshold=0)
    result = constraint.evaluate(())
    assert result.passed is True


def test_count_gte_with_positive_threshold_fails_on_empty() -> None:
    constraint = CountGteConstraint(table="sys_scope", threshold=1)
    result = constraint.evaluate(())
    assert result.passed is False


def test_count_gte_respects_filter() -> None:
    constraint = CountGteConstraint(table="sys_scope", threshold=2, filter=(("active", "true"),))
    records = (
        _record("r1", active="true"),
        _record("r2", active="true"),
        _record("r3", active="false"),
    )
    result = constraint.evaluate(records)
    assert result.passed is True
