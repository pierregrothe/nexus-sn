# tests/assessment/test_constraint_field_in.py
# Tests for FieldInConstraint.evaluate.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 02 AC4: field_in operator."""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.assessment.schemas.constraints import FieldInConstraint
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


def test_field_in_passes_when_all_in_set() -> None:
    constraint = FieldInConstraint(table="sys_scope", field="status", expected=("ok", "ready"))
    records = (_record("r1", status="ok"), _record("r2", status="ready"))
    result = constraint.evaluate(records)
    assert result.passed is True


def test_field_in_fails_when_any_outside_set() -> None:
    constraint = FieldInConstraint(table="sys_scope", field="status", expected=("ok", "ready"))
    records = (_record("r1", status="ok"), _record("r2", status="broken"))
    result = constraint.evaluate(records)
    assert result.passed is False
    assert result.affected_sys_ids == ("r2",)


def test_field_in_fails_on_empty_records() -> None:
    constraint = FieldInConstraint(table="sys_scope", field="status", expected=("ok",))
    result = constraint.evaluate(())
    assert result.passed is False
    assert "no matching records" in result.message


def test_field_in_missing_field_counts_as_failure() -> None:
    constraint = FieldInConstraint(table="sys_scope", field="status", expected=("ok",))
    records = (_record("r1"),)
    result = constraint.evaluate(records)
    assert result.passed is False
    assert result.affected_sys_ids == ("r1",)
