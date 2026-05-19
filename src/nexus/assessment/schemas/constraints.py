# src/nexus/assessment/schemas/constraints.py
# RuleConstraint discriminated union -- schema skeleton only.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Constraint variant schemas. Story 02 adds `.evaluate()` per variant.

Each variant uses Pydantic's `discriminator="operator"` tagged-union pattern.
The `FieldFilter` alias is a tuple of (field_name, expected_value) pairs that
get AND-ed together to subset records before the operator's check runs.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

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


class RecordExistsConstraint(BaseModel):
    """Assert at least one record matches the filter on the named table."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operator: Literal["record_exists"] = "record_exists"
    table: str = Field(..., min_length=1)
    filter: FieldFilter = ()


class FieldEqualsConstraint(BaseModel):
    """Assert every filtered record on `table` has `field == expected`."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operator: Literal["field_equals"] = "field_equals"
    table: str = Field(..., min_length=1)
    field: str = Field(..., min_length=1)
    expected: str
    filter: FieldFilter = ()


class FieldInConstraint(BaseModel):
    """Assert every filtered record's `field` value is in `expected` set."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operator: Literal["field_in"] = "field_in"
    table: str = Field(..., min_length=1)
    field: str = Field(..., min_length=1)
    expected: tuple[str, ...] = Field(..., min_length=1)
    filter: FieldFilter = ()


class CountGteConstraint(BaseModel):
    """Assert filter-matching record count is >= threshold."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operator: Literal["count_gte"] = "count_gte"
    table: str = Field(..., min_length=1)
    threshold: int = Field(..., ge=0)
    filter: FieldFilter = ()


class CountLteConstraint(BaseModel):
    """Assert filter-matching record count is <= threshold."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    operator: Literal["count_lte"] = "count_lte"
    table: str = Field(..., min_length=1)
    threshold: int = Field(..., ge=0)
    filter: FieldFilter = ()


type RuleConstraint = Annotated[
    RecordExistsConstraint
    | FieldEqualsConstraint
    | FieldInConstraint
    | CountGteConstraint
    | CountLteConstraint,
    Field(discriminator="operator"),
]
