# src/nexus/assessment/dsl.py
# Constraint evaluation primitives.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Shared ConstraintResult model + per-operator evaluation helpers.

Each `RuleConstraint` variant defined in `schemas/constraints.py` exposes
an `evaluate(records)` method that returns a `ConstraintResult`. The
result is uniform across operators so the RuleEngine (Story 03) can
compose results without dispatching on operator type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from nexus.assessment.schemas.constraints import FieldFilter
    from nexus.capture.models import ConfigRecord, SnFieldValue

__all__ = ["ConstraintResult", "filter_records", "record_field_value"]


class ConstraintResult(BaseModel):
    """Outcome of a single constraint evaluation against a record tuple.

    Attributes:
        passed: True iff the constraint's assertion holds.
        affected_sys_ids: Tuple of sys_ids that motivated the result.
            On pass: ids that satisfied the constraint. On fail: ids that
            triggered the failure (offending records).
        message: Human-readable summary for inclusion in Findings.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    passed: bool
    affected_sys_ids: tuple[str, ...] = Field(default=())
    message: str = ""


def record_field_value(record: ConfigRecord, field: str) -> str | None:
    """Return the string form of a record's field value or None if missing.

    Reference fields ({"value": ..., "display_value": ...}) collapse to
    their `value` (sys_id) so equality comparisons work uniformly.

    Args:
        record: The ConfigRecord to look up.
        field: Field name.

    Returns:
        The field's string value, or None if the field is absent.
    """
    raw: SnFieldValue | None = record.fields.get(field)
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get("value")
    return raw


def filter_records(
    records: tuple[ConfigRecord, ...], filter_pairs: FieldFilter
) -> tuple[ConfigRecord, ...]:
    """Return records that match every (field, expected) pair in the filter.

    Empty filter -> all records returned. Filter pairs AND together.

    Args:
        records: Input records.
        filter_pairs: Tuple of (field_name, expected_value) pairs.

    Returns:
        Subset of records satisfying every pair.
    """
    if not filter_pairs:
        return records
    matched: list[ConfigRecord] = []
    for record in records:
        if all(record_field_value(record, name) == expected for name, expected in filter_pairs):
            matched.append(record)
    return tuple(matched)
