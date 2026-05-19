# tests/assessment/test_rule_engine_evaluate.py
# Tests for RuleEngine.evaluate covering completeness, phase, dispatch, composition.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 03 acceptance tests for the pure evaluation engine."""

from __future__ import annotations

from nexus.assessment.context import GateContext
from nexus.assessment.engine import evaluate
from nexus.assessment.findings import Finding
from nexus.assessment.schemas.constraints import (
    FieldEqualsConstraint,
    RecordExistsConstraint,
)
from nexus.assessment.schemas.enums import Logic, Phase, Severity
from nexus.assessment.schemas.rule import AssessmentRule
from nexus.assessment.schemas.scope import CrossTableScope, TableScope
from nexus.capture.models import ConfigRecord
from tests.fakes.captures import make_capture_result, make_config_record
from tests.fakes.rulesets import make_assessment_rule


def _ctx(records: tuple[ConfigRecord, ...] = (), phase: Phase = Phase.PRE_APPLY) -> GateContext:
    return GateContext(
        capture=make_capture_result(records=records),
        apply_result=None,
        phase=phase,
    )


def test_evaluate_with_no_rules_returns_empty() -> None:
    assert evaluate((), _ctx()) == ()


def test_evaluate_skips_rule_with_mismatched_phase() -> None:
    rule = make_assessment_rule(phase=Phase.POST_APPLY)
    record = make_config_record(table="sys_scope")
    findings = evaluate((rule,), _ctx(records=(record,), phase=Phase.PRE_APPLY))
    assert findings == ()


def test_evaluate_emits_error_finding_on_missing_required_table() -> None:
    rule = make_assessment_rule(required_tables=("sys_scope", "sys_user"))
    record = make_config_record(table="sys_scope")
    findings = evaluate((rule,), _ctx(records=(record,)))
    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity is Severity.ERROR
    assert "sys_user" in finding.message
    assert finding.affected_sys_ids == ()


def test_evaluate_does_not_run_constraints_when_required_table_missing() -> None:
    rule = AssessmentRule(
        id="r",
        description="r",
        severity=Severity.WARNING,
        phase=Phase.PRE_APPLY,
        scope=CrossTableScope(),
        required_tables=("sys_user",),
        constraints=(RecordExistsConstraint(table="sys_user"),),
    )
    findings = evaluate((rule,), _ctx(records=()))
    assert len(findings) == 1
    assert findings[0].severity is Severity.ERROR


def test_evaluate_table_scope_filters_records_to_target_table() -> None:
    rule = make_assessment_rule(
        required_tables=("sys_scope",),
        constraints=(
            FieldEqualsConstraint(
                table="sys_scope",
                field="active",
                expected="true",
            ),
        ),
    )
    matching = make_config_record(sys_id="r1", table="sys_scope", fields={"active": "true"})
    other_table = make_config_record(sys_id="r2", table="sys_user", fields={"active": "false"})
    findings = evaluate((rule,), _ctx(records=(matching, other_table)))
    assert findings == ()


def test_evaluate_cross_table_scope_sees_all_records() -> None:
    rule = AssessmentRule(
        id="r",
        description="r",
        severity=Severity.WARNING,
        phase=Phase.PRE_APPLY,
        scope=CrossTableScope(),
        required_tables=("sys_scope", "sys_user"),
        constraints=(
            RecordExistsConstraint(table="sys_scope"),
            RecordExistsConstraint(table="sys_user"),
        ),
    )
    scope_rec = make_config_record(sys_id="s1", table="sys_scope")
    user_rec = make_config_record(sys_id="u1", table="sys_user")
    findings = evaluate((rule,), _ctx(records=(scope_rec, user_rec)))
    assert findings == ()


def test_evaluate_and_all_emits_finding_on_any_constraint_failure() -> None:
    rule = make_assessment_rule(
        required_tables=("sys_scope",),
        scope=TableScope(table="sys_scope"),
        constraints=(
            RecordExistsConstraint(table="sys_scope"),
            FieldEqualsConstraint(table="sys_scope", field="active", expected="true"),
        ),
    )
    record = make_config_record(table="sys_scope", fields={"active": "false"})
    findings = evaluate((rule,), _ctx(records=(record,)))
    assert len(findings) == 1
    assert findings[0].severity is Severity.ERROR


def test_evaluate_and_all_passes_when_all_constraints_pass() -> None:
    rule = make_assessment_rule(
        required_tables=("sys_scope",),
        scope=TableScope(table="sys_scope"),
        constraints=(
            RecordExistsConstraint(table="sys_scope"),
            FieldEqualsConstraint(table="sys_scope", field="active", expected="true"),
        ),
    )
    record = make_config_record(table="sys_scope", fields={"active": "true"})
    assert evaluate((rule,), _ctx(records=(record,))) == ()


def test_evaluate_or_any_passes_when_one_constraint_passes() -> None:
    rule = make_assessment_rule(
        logic=Logic.OR_ANY,
        required_tables=("sys_scope",),
        scope=TableScope(table="sys_scope"),
        constraints=(
            FieldEqualsConstraint(table="sys_scope", field="active", expected="never"),
            RecordExistsConstraint(table="sys_scope"),
        ),
    )
    record = make_config_record(table="sys_scope", fields={"active": "true"})
    findings = evaluate((rule,), _ctx(records=(record,)))
    assert findings == ()


def test_evaluate_or_any_emits_finding_when_all_constraints_fail() -> None:
    rule = make_assessment_rule(
        logic=Logic.OR_ANY,
        required_tables=("sys_scope",),
        scope=TableScope(table="sys_scope"),
        constraints=(
            FieldEqualsConstraint(table="sys_scope", field="active", expected="never"),
            FieldEqualsConstraint(table="sys_scope", field="active", expected="also-never"),
        ),
    )
    record = make_config_record(table="sys_scope", fields={"active": "true"})
    findings = evaluate((rule,), _ctx(records=(record,)))
    assert len(findings) == 1
    assert findings[0].message.startswith("OR_ANY: ")


def test_evaluate_propagates_rule_severity_to_finding() -> None:
    rule = make_assessment_rule(
        severity=Severity.WARNING,
        scope=TableScope(table="sys_scope"),
        constraints=(FieldEqualsConstraint(table="sys_scope", field="active", expected="never"),),
    )
    record = make_config_record(table="sys_scope", fields={"active": "true"})
    findings = evaluate((rule,), _ctx(records=(record,)))
    assert findings[0].severity is Severity.WARNING


def test_evaluate_returns_findings_in_input_rule_order() -> None:
    rule_a = make_assessment_rule(
        rule_id="rule-a",
        severity=Severity.ERROR,
        required_tables=("sys_scope",),
        scope=TableScope(table="sys_scope"),
        constraints=(FieldEqualsConstraint(table="sys_scope", field="active", expected="never"),),
    )
    rule_b = make_assessment_rule(
        rule_id="rule-b",
        severity=Severity.WARNING,
        required_tables=("sys_scope",),
        scope=TableScope(table="sys_scope"),
        constraints=(
            FieldEqualsConstraint(table="sys_scope", field="active", expected="also-never"),
        ),
    )
    record = make_config_record(table="sys_scope", fields={"active": "true"})
    findings = evaluate((rule_a, rule_b), _ctx(records=(record,)))
    assert tuple(f.rule_id for f in findings) == ("rule-a", "rule-b")


def test_evaluate_emits_finding_phase_from_context() -> None:
    rule = make_assessment_rule(
        phase=Phase.STANDALONE,
        scope=TableScope(table="sys_scope"),
        constraints=(FieldEqualsConstraint(table="sys_scope", field="active", expected="true"),),
    )
    record = make_config_record(table="sys_scope", fields={"active": "false"})
    findings = evaluate((rule,), _ctx(records=(record,), phase=Phase.STANDALONE))
    assert findings[0].phase is Phase.STANDALONE


def test_evaluate_does_not_mutate_inputs() -> None:
    rule = make_assessment_rule()
    record = make_config_record(table="sys_scope")
    rules = (rule,)
    ctx = _ctx(records=(record,))
    evaluate(rules, ctx)
    assert rules == (rule,)
    assert ctx.capture.records == (record,)


def test_finding_model_accepts_empty_affected_ids_by_default() -> None:
    finding = Finding(rule_id="r", severity=Severity.INFO, message="m", phase=Phase.STANDALONE)
    assert finding.affected_sys_ids == ()
