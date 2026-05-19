# src/nexus/assessment/schemas/scope.py
# RuleScope discriminated union: table or cross-table dispatch.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Rule scope -- declares whether a rule evaluates per-table or cross-table."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["CrossTableScope", "RuleScope", "TableScope"]


class TableScope(BaseModel):
    """Per-table scope -- engine routes only records whose `table` matches.

    Attributes:
        kind: Discriminator literal `"table"`.
        table: ServiceNow table name (e.g. `sys_scope`).
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["table"] = "table"
    table: str = Field(..., min_length=1)


class CrossTableScope(BaseModel):
    """Cross-table scope -- engine passes the full record tuple to constraints."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    kind: Literal["cross-table"] = "cross-table"


type RuleScope = Annotated[TableScope | CrossTableScope, Field(discriminator="kind")]
