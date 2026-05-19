# tests/assessment/test_constraint_field_equals.py
# Tests for FieldEqualsConstraint.evaluate.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 02 AC3, AC9: field_equals operator."""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.assessment.schemas.constraints import FieldEqualsConstraint
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


def test_field_equals_passes_when_all_match() -> None:
    constraint = FieldEqualsConstraint(table="sys_scope", field="active", expected="true")
    records = (_record("r1", active="true"), _record("r2", active="true"))
    result = constraint.evaluate(records)
    assert result.passed is True
    assert set(result.affected_sys_ids) == {"r1", "r2"}


def test_field_equals_fails_when_any_differs() -> None:
    constraint = FieldEqualsConstraint(table="sys_scope", field="active", expected="true")
    records = (_record("r1", active="true"), _record("r2", active="false"))
    result = constraint.evaluate(records)
    assert result.passed is False
    assert result.affected_sys_ids == ("r2",)


def test_field_equals_fails_on_empty_records() -> None:
    constraint = FieldEqualsConstraint(table="sys_scope", field="active", expected="true")
    result = constraint.evaluate(())
    assert result.passed is False
    assert "no matching records" in result.message


def test_field_equals_fails_when_filter_matches_nothing() -> None:
    constraint = FieldEqualsConstraint(
        table="sys_scope",
        field="active",
        expected="true",
        filter=(("vendor", "SN"),),
    )
    records = (_record("r1", active="true", vendor="other"),)
    result = constraint.evaluate(records)
    assert result.passed is False
    assert "no matching records" in result.message


def test_field_equals_missing_field_counts_as_failure() -> None:
    constraint = FieldEqualsConstraint(table="sys_scope", field="active", expected="true")
    records = (_record("r1"),)
    result = constraint.evaluate(records)
    assert result.passed is False
    assert result.affected_sys_ids == ("r1",)
