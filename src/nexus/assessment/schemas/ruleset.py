# src/nexus/assessment/schemas/ruleset.py
# Ruleset -- a YAML-authored collection of AssessmentRules.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Pydantic model for a complete ruleset file (templates/assessments/*.yaml)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from nexus.assessment.schemas.rule import AssessmentRule

__all__ = ["Ruleset"]


class Ruleset(BaseModel):
    """A named, versioned collection of AssessmentRules.

    Attributes:
        id: Unique ruleset identifier (filename slug).
        version: Semantic version string (e.g. `1.0.0`).
        description: Human-readable summary.
        applies_to: Tuple of template ids the ruleset applies to.
            Use `("*",)` for rulesets that apply to all templates.
        rules: Tuple of AssessmentRules evaluated together.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    applies_to: tuple[str, ...] = Field(..., min_length=1)
    rules: tuple[AssessmentRule, ...] = Field(..., min_length=1)
