# tests/assessment/test_ruleset_schema.py
# Schema-level tests for Story 01: Ruleset + AssessmentRule + scope + constraints.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Pydantic validation tests for the rule schema family."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from nexus.assessment.schemas.constraints import (
    CountGteConstraint,
    CountLteConstraint,
    FieldEqualsConstraint,
    FieldInConstraint,
    RecordExistsConstraint,
)
from nexus.assessment.schemas.enums import Logic, Phase, Severity
from nexus.assessment.schemas.rule import AssessmentRule
from nexus.assessment.schemas.ruleset import Ruleset
from nexus.assessment.schemas.scope import CrossTableScope, TableScope
from tests.fakes.rulesets import (
    make_assessment_rule,
    make_record_exists_constraint,
    make_ruleset,
)


def test_ruleset_constructs_with_minimum_fields() -> None:
    ruleset = make_ruleset()
    assert ruleset.id == "sample"
    assert ruleset.version == "1.0.0"
    assert len(ruleset.rules) == 1
    assert ruleset.applies_to == ("*",)


def test_ruleset_rejects_empty_rules_tuple() -> None:
    with pytest.raises(ValidationError):
        Ruleset(
            id="x",
            version="1.0.0",
            description="empty",
            applies_to=("*",),
            rules=(),
        )


def test_ruleset_rejects_empty_applies_to() -> None:
    with pytest.raises(ValidationError):
        Ruleset(
            id="x",
            version="1.0.0",
            description="empty",
            applies_to=(),
            rules=(make_assessment_rule(),),
        )


def test_ruleset_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Ruleset.model_validate(
            {
                "id": "x",
                "version": "1.0.0",
                "description": "x",
                "applies_to": ["*"],
                "rules": [
                    {
                        "id": "r",
                        "description": "r",
                        "severity": "ERROR",
                        "phase": "PRE_APPLY",
                        "scope": {"kind": "table", "table": "sys_scope"},
                        "required_tables": ["sys_scope"],
                        "logic": "AND_ALL",
                        "constraints": [
                            {
                                "operator": "record_exists",
                                "table": "sys_scope",
                                "filter": [],
                            }
                        ],
                    }
                ],
                "garbage_field": True,
            }
        )


def test_assessment_rule_constructs_with_minimum_fields() -> None:
    rule = make_assessment_rule()
    assert rule.severity is Severity.ERROR
    assert rule.phase is Phase.PRE_APPLY
    assert rule.logic is Logic.AND_ALL
    assert len(rule.constraints) == 1


def test_assessment_rule_is_frozen() -> None:
    rule = make_assessment_rule()
    with pytest.raises(ValidationError):
        rule.id = "different"


def test_assessment_rule_requires_constraints() -> None:
    with pytest.raises(ValidationError):
        AssessmentRule(
            id="r",
            description="r",
            severity=Severity.ERROR,
            phase=Phase.PRE_APPLY,
            scope=TableScope(table="sys_scope"),
            required_tables=("sys_scope",),
            constraints=(),
        )


def test_assessment_rule_requires_at_least_one_required_table() -> None:
    with pytest.raises(ValidationError):
        AssessmentRule(
            id="r",
            description="r",
            severity=Severity.ERROR,
            phase=Phase.PRE_APPLY,
            scope=TableScope(table="sys_scope"),
            required_tables=(),
            constraints=(make_record_exists_constraint(table="sys_scope"),),
        )


def test_assessment_rule_rejects_constraint_table_not_in_required() -> None:
    with pytest.raises(ValidationError) as exc_info:
        AssessmentRule(
            id="r",
            description="r",
            severity=Severity.ERROR,
            phase=Phase.PRE_APPLY,
            scope=CrossTableScope(),
            required_tables=("sys_scope",),
            constraints=(make_record_exists_constraint(table="sys_user"),),
        )
    assert "not in required_tables" in str(exc_info.value)


def test_assessment_rule_table_scope_rejects_constraint_with_different_table() -> None:
    with pytest.raises(ValidationError) as exc_info:
        AssessmentRule(
            id="r",
            description="r",
            severity=Severity.ERROR,
            phase=Phase.PRE_APPLY,
            scope=TableScope(table="sys_scope"),
            required_tables=("sys_scope", "sys_user"),
            constraints=(make_record_exists_constraint(table="sys_user"),),
        )
    assert "scope.table" in str(exc_info.value)


def test_assessment_rule_cross_table_scope_allows_multi_table_constraints() -> None:
    rule = AssessmentRule(
        id="r",
        description="r",
        severity=Severity.ERROR,
        phase=Phase.STANDALONE,
        scope=CrossTableScope(),
        required_tables=("sys_scope", "sys_user"),
        constraints=(
            make_record_exists_constraint(table="sys_scope"),
            make_record_exists_constraint(table="sys_user"),
        ),
    )
    assert len(rule.constraints) == 2


def test_severity_enum_values() -> None:
    assert Severity.ERROR.value == "ERROR"
    assert Severity.WARNING.value == "WARNING"
    assert Severity.INFO.value == "INFO"


def test_phase_enum_values() -> None:
    assert Phase.PRE_APPLY.value == "PRE_APPLY"
    assert Phase.POST_APPLY.value == "POST_APPLY"
    assert Phase.STANDALONE.value == "STANDALONE"


def test_logic_enum_values() -> None:
    assert Logic.AND_ALL.value == "AND_ALL"
    assert Logic.OR_ANY.value == "OR_ANY"


def test_table_scope_kind_is_literal_table() -> None:
    scope = TableScope(table="sys_scope")
    assert scope.kind == "table"


def test_cross_table_scope_kind_is_literal_cross_table() -> None:
    scope = CrossTableScope()
    assert scope.kind == "cross-table"


def test_scope_discriminated_union_dispatches_table_kind() -> None:
    rule = make_assessment_rule(scope=TableScope(table="sys_scope"))
    assert isinstance(rule.scope, TableScope)


def test_scope_discriminated_union_dispatches_cross_table_kind() -> None:
    rule = make_assessment_rule(
        scope=CrossTableScope(),
        required_tables=("sys_scope",),
        constraints=(make_record_exists_constraint(table="sys_scope"),),
    )
    assert isinstance(rule.scope, CrossTableScope)


def test_record_exists_constraint_discriminator() -> None:
    constraint = RecordExistsConstraint(table="sys_scope")
    assert constraint.operator == "record_exists"


def test_field_equals_constraint_discriminator() -> None:
    constraint = FieldEqualsConstraint(table="sys_scope", field="active", expected="true")
    assert constraint.operator == "field_equals"


def test_field_in_constraint_discriminator() -> None:
    constraint = FieldInConstraint(table="sys_scope", field="status", expected=("ok", "ready"))
    assert constraint.operator == "field_in"


def test_count_gte_constraint_discriminator() -> None:
    constraint = CountGteConstraint(table="sys_scope", threshold=1)
    assert constraint.operator == "count_gte"


def test_count_lte_constraint_discriminator() -> None:
    constraint = CountLteConstraint(table="sys_scope", threshold=10)
    assert constraint.operator == "count_lte"


def test_count_gte_constraint_rejects_negative_threshold() -> None:
    with pytest.raises(ValidationError):
        CountGteConstraint(table="sys_scope", threshold=-1)


def test_field_in_constraint_rejects_empty_expected() -> None:
    with pytest.raises(ValidationError):
        FieldInConstraint(table="sys_scope", field="status", expected=())
