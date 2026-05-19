# src/nexus/assessment/schemas/rule.py
# AssessmentRule -- one declarative readiness/validation/health check.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Pydantic model for a single assessment rule.

Cross-field validation enforces that every constraint's `table` is listed
in `required_tables`. This prevents silent false-PASS verdicts when capture
is incomplete -- the engine pre-check (Story 03) raises ERROR Findings when
a required table is missing from the CaptureResult.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nexus.assessment.schemas.constraints import RuleConstraint
from nexus.assessment.schemas.enums import Logic, Phase, Severity
from nexus.assessment.schemas.scope import RuleScope, TableScope

__all__ = ["AssessmentRule"]


class AssessmentRule(BaseModel):
    """One declarative rule evaluated by the RuleEngine.

    Attributes:
        id: Unique identifier within the parent Ruleset.
        description: Human-readable summary used in Finding messages.
        severity: Severity of the emitted Finding when the rule fails.
        phase: Lifecycle phase this rule applies to.
        scope: Per-table or cross-table dispatch.
        required_tables: Tables the rule needs captured to evaluate.
        logic: Boolean composition over `constraints`.
        constraints: Flat tuple combined by `logic`.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    severity: Severity
    phase: Phase
    scope: RuleScope
    required_tables: tuple[str, ...] = Field(..., min_length=1)
    logic: Logic = Logic.AND_ALL
    constraints: tuple[RuleConstraint, ...] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _check_constraint_tables_in_required(self) -> Self:
        """Every constraint.table MUST appear in required_tables."""
        required = set(self.required_tables)
        for constraint in self.constraints:
            if constraint.table not in required:
                raise ValueError(
                    f"rule {self.id!r}: constraint references table "
                    f"{constraint.table!r} which is not in required_tables "
                    f"{tuple(self.required_tables)}"
                )
        return self

    @model_validator(mode="after")
    def _check_scope_matches_constraint_tables(self) -> Self:
        """For TableScope, every constraint must target the scope's table."""
        if isinstance(self.scope, TableScope):
            for constraint in self.constraints:
                if constraint.table != self.scope.table:
                    raise ValueError(
                        f"rule {self.id!r}: scope.table is "
                        f"{self.scope.table!r} but constraint targets "
                        f"{constraint.table!r}"
                    )
        return self
