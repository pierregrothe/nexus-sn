# tests/assessment/test_gates.py
# Tests for Gate1Readiness + Gate2Validation + HealthScan.
# Author: Pierre Grothe
# Date: 2026-05-19

"""Story 04 AC5-AC12: gate implementations + protocol membership."""

from __future__ import annotations

from nexus.assessment.context import ApplyResult, GateContext
from nexus.assessment.gate import GateProtocol
from nexus.assessment.gates import Gate1Readiness, Gate2Validation, HealthScan
from nexus.assessment.schemas.constraints import FieldEqualsConstraint
from nexus.assessment.schemas.enums import Phase, Severity
from nexus.assessment.schemas.rule import AssessmentRule
from nexus.assessment.schemas.scope import TableScope
from nexus.assessment.verdict import GateVerdict
from tests.fakes.captures import make_capture_result, make_config_record
from tests.fakes.gates import FakeGate
from tests.fakes.rulesets import make_assessment_rule, make_ruleset


def _ctx(*, phase: Phase, apply_result: ApplyResult | None = None) -> GateContext:
    record = make_config_record(table="sys_scope", fields={"active": "true"})
    return GateContext(
        capture=make_capture_result(records=(record,)),
        apply_result=apply_result,
        phase=phase,
    )


def test_gate1_readiness_evaluates_pre_apply_rules() -> None:
    rule = make_assessment_rule(phase=Phase.PRE_APPLY)
    ruleset = make_ruleset(rules=(rule,))
    gate = Gate1Readiness(ruleset=ruleset, template_id="acme")
    report = gate.evaluate(_ctx(phase=Phase.PRE_APPLY))
    assert report.verdict is GateVerdict.PASS
    assert report.template_id == "acme"
    assert report.ruleset_id == ruleset.id


def test_gate1_readiness_errors_on_wrong_phase() -> None:
    rule = make_assessment_rule(phase=Phase.PRE_APPLY)
    ruleset = make_ruleset(rules=(rule,))
    gate = Gate1Readiness(ruleset=ruleset, template_id="acme")
    report = gate.evaluate(_ctx(phase=Phase.STANDALONE))
    assert report.verdict is GateVerdict.ERROR
    assert any("PRE_APPLY" in f.message for f in report.findings)


def test_gate1_readiness_skips_non_pre_apply_rules_in_ruleset() -> None:
    pre_rule = make_assessment_rule(rule_id="pre", phase=Phase.PRE_APPLY)
    post_rule = make_assessment_rule(rule_id="post", phase=Phase.POST_APPLY)
    ruleset = make_ruleset(rules=(pre_rule, post_rule))
    gate = Gate1Readiness(ruleset=ruleset, template_id="acme")
    report = gate.evaluate(_ctx(phase=Phase.PRE_APPLY))
    assert report.summary.rules_evaluated == 1


def test_gate2_validation_requires_apply_result() -> None:
    rule = make_assessment_rule(phase=Phase.POST_APPLY)
    ruleset = make_ruleset(rules=(rule,))
    gate = Gate2Validation(ruleset=ruleset, template_id="acme")
    report = gate.evaluate(_ctx(phase=Phase.POST_APPLY, apply_result=None))
    assert report.verdict is GateVerdict.ERROR
    assert any("apply_result" in f.message for f in report.findings)


def test_gate2_validation_evaluates_post_apply_rules_with_apply_result() -> None:
    rule = make_assessment_rule(phase=Phase.POST_APPLY)
    ruleset = make_ruleset(rules=(rule,))
    gate = Gate2Validation(ruleset=ruleset, template_id="acme")
    report = gate.evaluate(_ctx(phase=Phase.POST_APPLY, apply_result=ApplyResult()))
    assert report.verdict is GateVerdict.PASS


def test_gate2_validation_errors_on_wrong_phase() -> None:
    rule = make_assessment_rule(phase=Phase.POST_APPLY)
    ruleset = make_ruleset(rules=(rule,))
    gate = Gate2Validation(ruleset=ruleset, template_id="acme")
    report = gate.evaluate(_ctx(phase=Phase.PRE_APPLY))
    assert report.verdict is GateVerdict.ERROR


def test_health_scan_evaluates_standalone_rules() -> None:
    rule = make_assessment_rule(phase=Phase.STANDALONE)
    ruleset = make_ruleset(rules=(rule,))
    gate = HealthScan(ruleset=ruleset)
    report = gate.evaluate(_ctx(phase=Phase.STANDALONE))
    assert report.verdict is GateVerdict.PASS
    assert report.template_id is None


def test_health_scan_errors_on_wrong_phase() -> None:
    rule = make_assessment_rule(phase=Phase.STANDALONE)
    ruleset = make_ruleset(rules=(rule,))
    gate = HealthScan(ruleset=ruleset)
    report = gate.evaluate(_ctx(phase=Phase.PRE_APPLY))
    assert report.verdict is GateVerdict.ERROR


def test_gates_satisfy_gate_protocol_runtime_check() -> None:
    rule = make_assessment_rule(phase=Phase.PRE_APPLY)
    ruleset = make_ruleset(rules=(rule,))
    gate1 = Gate1Readiness(ruleset=ruleset, template_id="t")
    gate2 = Gate2Validation(ruleset=ruleset, template_id="t")
    health = HealthScan(ruleset=ruleset)
    assert isinstance(gate1, GateProtocol)
    assert isinstance(gate2, GateProtocol)
    assert isinstance(health, GateProtocol)


def test_fake_gate_records_evaluated_ctx_and_returns_canned_report() -> None:
    rule = make_assessment_rule(phase=Phase.STANDALONE)
    ruleset = make_ruleset(rules=(rule,))
    canned = HealthScan(ruleset=ruleset).evaluate(_ctx(phase=Phase.STANDALONE))
    fake = FakeGate(report=canned)
    ctx = _ctx(phase=Phase.STANDALONE)
    got = fake.evaluate(ctx)
    assert got is canned
    assert fake.evaluated_ctxs == (ctx,)


def test_gate1_readiness_warning_severity_yields_block_verdict() -> None:
    rule = AssessmentRule(
        id="warn-rule",
        description="warn",
        severity=Severity.WARNING,
        phase=Phase.PRE_APPLY,
        scope=TableScope(table="sys_scope"),
        required_tables=("sys_scope",),
        constraints=(FieldEqualsConstraint(table="sys_scope", field="active", expected="never"),),
    )
    ruleset = make_ruleset(rules=(rule,))
    gate = Gate1Readiness(ruleset=ruleset, template_id="t")
    report = gate.evaluate(_ctx(phase=Phase.PRE_APPLY))
    assert report.verdict is GateVerdict.BLOCK
