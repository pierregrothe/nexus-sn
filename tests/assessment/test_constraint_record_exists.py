# tests/assessment/test_constraint_record_exists.py
# Tests for RecordExistsConstraint.evaluate.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 02 AC2, AC7, AC8, AC10: record_exists operator."""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.assessment.schemas.constraints import RecordExistsConstraint
from nexus.capture.models import ConfigRecord

NOW = datetime.now(UTC)


def _record(sys_id: str, table: str = "sys_scope", **fields: str) -> ConfigRecord:
    return ConfigRecord(
        sys_id=sys_id,
        table=table,
        scope_sys_id="s1",
        scope_name="x_app",
        captured_at=NOW,
        fields=dict(fields),
        parent_sys_id=None,
    )


def test_record_exists_passes_when_records_match_no_filter() -> None:
    constraint = RecordExistsConstraint(table="sys_scope")
    records = (_record("r1"), _record("r2"))
    result = constraint.evaluate(records)
    assert result.passed is True
    assert set(result.affected_sys_ids) == {"r1", "r2"}


def test_record_exists_passes_with_filter_match() -> None:
    constraint = RecordExistsConstraint(table="sys_scope", filter=(("active", "true"),))
    records = (
        _record("r1", active="true"),
        _record("r2", active="false"),
    )
    result = constraint.evaluate(records)
    assert result.passed is True
    assert result.affected_sys_ids == ("r1",)


def test_record_exists_fails_on_empty_records() -> None:
    constraint = RecordExistsConstraint(table="sys_scope")
    result = constraint.evaluate(())
    assert result.passed is False
    assert result.affected_sys_ids == ()


def test_record_exists_fails_when_filter_matches_nothing() -> None:
    constraint = RecordExistsConstraint(table="sys_scope", filter=(("active", "true"),))
    records = (_record("r1", active="false"),)
    result = constraint.evaluate(records)
    assert result.passed is False


def test_record_exists_filter_ands_pairs() -> None:
    constraint = RecordExistsConstraint(
        table="sys_scope",
        filter=(("active", "true"), ("vendor", "SN")),
    )
    records = (
        _record("r1", active="true", vendor="SN"),
        _record("r2", active="true", vendor="other"),
    )
    result = constraint.evaluate(records)
    assert result.passed is True
    assert result.affected_sys_ids == ("r1",)


def test_record_exists_is_pure_no_mutation() -> None:
    constraint = RecordExistsConstraint(table="sys_scope")
    records = (_record("r1"),)
    constraint.evaluate(records)
    assert records[0].sys_id == "r1"


def test_record_exists_does_not_raise_on_missing_filter_field() -> None:
    constraint = RecordExistsConstraint(table="sys_scope", filter=(("does_not_exist", "x"),))
    result = constraint.evaluate((_record("r1"),))
    assert result.passed is False
