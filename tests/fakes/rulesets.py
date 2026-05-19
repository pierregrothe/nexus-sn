# tests/fakes/rulesets.py
# Canned Ruleset and AssessmentRule fixtures for assessment tests.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Builder helpers for assessment rule fixtures.

Tests construct rule/ruleset instances via these helpers so the same
sample shape can be reused across schema, engine, gate, and CLI tests
without duplicating long Pydantic constructor calls.
"""

from __future__ import annotations

from nexus.assessment.schemas.constraints import (
    FieldEqualsConstraint,
    FieldFilter,
    RecordExistsConstraint,
    RuleConstraint,
)
from nexus.assessment.schemas.enums import Logic, Phase, Severity
from nexus.assessment.schemas.rule import AssessmentRule
from nexus.assessment.schemas.ruleset import Ruleset
from nexus.assessment.schemas.scope import RuleScope, TableScope

__all__ = [
    "make_assessment_rule",
    "make_record_exists_constraint",
    "make_ruleset",
    "sample_pre_apply_rule",
    "sample_ruleset",
]


def make_record_exists_constraint(
    *, table: str = "sys_scope", filter_: FieldFilter = ()
) -> RecordExistsConstraint:
    """Create a minimal `record_exists` constraint."""
    return RecordExistsConstraint(table=table, filter=filter_)


def make_assessment_rule(
    *,
    rule_id: str = "rule-1",
    description: str = "sample rule",
    severity: Severity = Severity.ERROR,
    phase: Phase = Phase.PRE_APPLY,
    scope: RuleScope | None = None,
    required_tables: tuple[str, ...] = ("sys_scope",),
    logic: Logic = Logic.AND_ALL,
    constraints: tuple[RuleConstraint, ...] | None = None,
) -> AssessmentRule:
    """Build a minimal AssessmentRule with sensible defaults.

    Args:
        rule_id: Identifier for the rule.
        description: Human-readable description.
        severity: Severity propagated to emitted Findings.
        phase: Lifecycle phase this rule applies to.
        scope: Optional scope; defaults to TableScope(table=required_tables[0]).
        required_tables: Tables the rule needs captured.
        logic: AND_ALL or OR_ANY.
        constraints: Constraint tuple; defaults to a single record_exists.

    Returns:
        Constructed AssessmentRule.
    """
    resolved_scope: RuleScope = scope or TableScope(table=required_tables[0])
    resolved_constraints: tuple[RuleConstraint, ...] = constraints or (
        make_record_exists_constraint(table=required_tables[0]),
    )
    return AssessmentRule(
        id=rule_id,
        description=description,
        severity=severity,
        phase=phase,
        scope=resolved_scope,
        required_tables=required_tables,
        logic=logic,
        constraints=resolved_constraints,
    )


def make_ruleset(
    *,
    ruleset_id: str = "sample",
    version: str = "1.0.0",
    description: str = "sample ruleset",
    applies_to: tuple[str, ...] = ("*",),
    rules: tuple[AssessmentRule, ...] | None = None,
) -> Ruleset:
    """Build a Ruleset with sensible defaults."""
    resolved_rules: tuple[AssessmentRule, ...] = rules or (make_assessment_rule(),)
    return Ruleset(
        id=ruleset_id,
        version=version,
        description=description,
        applies_to=applies_to,
        rules=resolved_rules,
    )


def sample_pre_apply_rule() -> AssessmentRule:
    """Compose a representative two-constraint PRE_APPLY rule.

    Useful as a generic fixture in rule-engine tests where the precise
    shape does not matter -- only that the rule has multiple constraints
    over one table.
    """
    constraints = (
        make_record_exists_constraint(table="sys_scope"),
        FieldEqualsConstraint(
            table="sys_scope",
            field="active",
            expected="true",
            filter=(),
        ),
    )
    return make_assessment_rule(
        rule_id="scope-active",
        description="scope must exist and be active",
        constraints=constraints,
    )


def sample_ruleset() -> Ruleset:
    """Compose a representative ruleset with a single rule."""
    return make_ruleset(rules=(sample_pre_apply_rule(),))
