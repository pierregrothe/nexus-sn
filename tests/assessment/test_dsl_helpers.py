# tests/assessment/test_dsl_helpers.py
# Tests for shared dsl helpers (filter_records, record_field_value, ConstraintResult).
# Author: Pierre Grothe
# Date: 2026-05-19

"""Coverage for nexus.assessment.dsl helpers consumed by all constraints."""

from __future__ import annotations

from datetime import UTC, datetime

from nexus.assessment.dsl import ConstraintResult, filter_records, record_field_value
from nexus.capture.models import ConfigRecord, SnFieldValue, SnRefField

NOW = datetime.now(UTC)


def _record(**fields: SnFieldValue) -> ConfigRecord:
    return ConfigRecord(
        sys_id="r1",
        table="sys_scope",
        scope_sys_id="s1",
        scope_name="x",
        captured_at=NOW,
        fields=fields,
        parent_sys_id=None,
    )


def test_record_field_value_returns_plain_string() -> None:
    record = _record(name="My Scope")
    assert record_field_value(record, "name") == "My Scope"


def test_record_field_value_returns_value_of_reference_field() -> None:
    ref: SnRefField = {"value": "sys_abc", "display_value": "Global"}
    record = _record(sys_scope=ref)
    assert record_field_value(record, "sys_scope") == "sys_abc"


def test_record_field_value_returns_none_when_missing() -> None:
    record = _record(name="x")
    assert record_field_value(record, "missing") is None


def test_filter_records_with_empty_filter_returns_all() -> None:
    a = _record(name="a")
    b = _record(name="b")
    assert filter_records((a, b), ()) == (a, b)


def test_filter_records_matches_single_pair() -> None:
    a = _record(name="a")
    b = _record(name="b")
    assert filter_records((a, b), (("name", "a"),)) == (a,)


def test_filter_records_ands_multiple_pairs() -> None:
    a = _record(name="a", active="true")
    b = _record(name="a", active="false")
    assert filter_records((a, b), (("name", "a"), ("active", "true"))) == (a,)


def test_constraint_result_defaults() -> None:
    result = ConstraintResult(passed=True)
    assert result.affected_sys_ids == ()
    assert result.message == ""
