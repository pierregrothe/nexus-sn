# src/nexus/assessment/schemas/constraints.py
# RuleConstraint discriminated union -- schema + .evaluate() per variant.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Constraint variant schemas and their evaluation logic.

Each variant uses Pydantic's `discriminator="operator"` tagged-union pattern
and exposes `evaluate(records) -> ConstraintResult`. The `FieldFilter` alias
is a tuple of (field_name, expected_value) pairs AND-ed together to subset
records before the operator's check runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from nexus.assessment.dsl import ConstraintResult, filter_records, record_field_value

if TYPE_CHECKING:
    from nexus.capture.models import ConfigRecord

__all__ = [
    "CountGteConstraint",
    "CountLteConstraint",
    "FieldEqualsConstraint",
    "FieldFilter",
    "FieldFilterPair",
    "FieldInConstraint",
    "RecordExistsConstraint",
    "RuleConstraint",
]


type FieldFilterPair = tuple[str, str]
type FieldFilter = tuple[FieldFilterPair, ...]


def _affected_ids(records: tuple[ConfigRecord, ...]) -> tuple[str, ...]:
    return tuple(record.sys_id for record in records)


class RecordExistsConstraint(BaseModel):
    """Assert at least one record matches the filter on the named table."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operator: Literal["record_exists"] = "record_exists"
    table: str = Field(..., min_length=1)
    filter: FieldFilter = ()

    def evaluate(self, records: tuple[ConfigRecord, ...]) -> ConstraintResult:
        """Pass if at least one record on `table` matches every filter pair."""
        matched = filter_records(records, self.filter)
        if matched:
            return ConstraintResult(
                passed=True,
                affected_sys_ids=_affected_ids(matched),
                message=f"record_exists on {self.table!r}: {len(matched)} matched",
            )
        return ConstraintResult(
            passed=False,
            affected_sys_ids=(),
            message=f"record_exists on {self.table!r}: no records matched",
        )


class FieldEqualsConstraint(BaseModel):
    """Assert every filtered record on `table` has `field == expected`."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operator: Literal["field_equals"] = "field_equals"
    table: str = Field(..., min_length=1)
    field: str = Field(..., min_length=1)
    expected: str
    filter: FieldFilter = ()

    def evaluate(self, records: tuple[ConfigRecord, ...]) -> ConstraintResult:
        """Pass iff every filter-matching record has field == expected."""
        matched = filter_records(records, self.filter)
        if not matched:
            return ConstraintResult(
                passed=False,
                affected_sys_ids=(),
                message=f"field_equals on {self.table!r}: no matching records for filter",
            )
        failed = tuple(
            record for record in matched if record_field_value(record, self.field) != self.expected
        )
        if not failed:
            return ConstraintResult(
                passed=True,
                affected_sys_ids=_affected_ids(matched),
                message=(
                    f"field_equals on {self.table}.{self.field}: "
                    f"all {len(matched)} records equal {self.expected!r}"
                ),
            )
        return ConstraintResult(
            passed=False,
            affected_sys_ids=_affected_ids(failed),
            message=(
                f"field_equals on {self.table}.{self.field}: "
                f"{len(failed)} records do not equal {self.expected!r}"
            ),
        )


class FieldInConstraint(BaseModel):
    """Assert every filtered record's `field` value is in `expected` set."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operator: Literal["field_in"] = "field_in"
    table: str = Field(..., min_length=1)
    field: str = Field(..., min_length=1)
    expected: tuple[str, ...] = Field(..., min_length=1)
    filter: FieldFilter = ()

    def evaluate(self, records: tuple[ConfigRecord, ...]) -> ConstraintResult:
        """Pass iff every filter-matching record's field value is in expected."""
        matched = filter_records(records, self.filter)
        if not matched:
            return ConstraintResult(
                passed=False,
                affected_sys_ids=(),
                message=f"field_in on {self.table!r}: no matching records for filter",
            )
        allowed = set(self.expected)
        failed = tuple(
            record for record in matched if record_field_value(record, self.field) not in allowed
        )
        if not failed:
            return ConstraintResult(
                passed=True,
                affected_sys_ids=_affected_ids(matched),
                message=(
                    f"field_in on {self.table}.{self.field}: "
                    f"all {len(matched)} records in expected set"
                ),
            )
        return ConstraintResult(
            passed=False,
            affected_sys_ids=_affected_ids(failed),
            message=(
                f"field_in on {self.table}.{self.field}: "
                f"{len(failed)} records outside expected set"
            ),
        )


class CountGteConstraint(BaseModel):
    """Assert filter-matching record count is >= threshold."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operator: Literal["count_gte"] = "count_gte"
    table: str = Field(..., min_length=1)
    threshold: int = Field(..., ge=0)
    filter: FieldFilter = ()

    def evaluate(self, records: tuple[ConfigRecord, ...]) -> ConstraintResult:
        """Pass iff len(filter-matching records) >= threshold."""
        matched = filter_records(records, self.filter)
        count = len(matched)
        if count >= self.threshold:
            return ConstraintResult(
                passed=True,
                affected_sys_ids=_affected_ids(matched),
                message=f"count_gte on {self.table!r}: {count} >= {self.threshold}",
            )
        return ConstraintResult(
            passed=False,
            affected_sys_ids=_affected_ids(matched),
            message=f"count_gte on {self.table!r}: {count} < {self.threshold}",
        )


class CountLteConstraint(BaseModel):
    """Assert filter-matching record count is <= threshold."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operator: Literal["count_lte"] = "count_lte"
    table: str = Field(..., min_length=1)
    threshold: int = Field(..., ge=0)
    filter: FieldFilter = ()

    def evaluate(self, records: tuple[ConfigRecord, ...]) -> ConstraintResult:
        """Pass iff len(filter-matching records) <= threshold."""
        matched = filter_records(records, self.filter)
        count = len(matched)
        if count <= self.threshold:
            return ConstraintResult(
                passed=True,
                affected_sys_ids=_affected_ids(matched),
                message=f"count_lte on {self.table!r}: {count} <= {self.threshold}",
            )
        return ConstraintResult(
            passed=False,
            affected_sys_ids=_affected_ids(matched),
            message=f"count_lte on {self.table!r}: {count} > {self.threshold}",
        )


type RuleConstraint = Annotated[
    RecordExistsConstraint
    | FieldEqualsConstraint
    | FieldInConstraint
    | CountGteConstraint
    | CountLteConstraint,
    Field(discriminator="operator"),
]
