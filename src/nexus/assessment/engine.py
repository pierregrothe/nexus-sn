# src/nexus/assessment/engine.py
# Pure rule-evaluation engine.
# Author: Pierre Grothe
# Date: 2026-05-19

"""RuleEngine.evaluate: pure function from (rules, ctx) to findings.

Pipeline per rule:
1. Skip rules whose phase does not match ctx.phase (silent filter -- normal
   cross-gate dispatch, not a failure).
2. Verify every entry in rule.required_tables is present in
   ctx.capture.by_table(); missing tables emit an ERROR Finding and the
   rule's constraints are NOT evaluated.
3. Dispatch records by rule.scope (per-table slice or full record tuple).
4. Evaluate each constraint, compose under rule.logic.
5. Emit a Finding only when the rule fails.
"""

from __future__ import annotations

from collections.abc import Iterable

from nexus.assessment.context import GateContext
from nexus.assessment.dsl import ConstraintResult
from nexus.assessment.findings import Finding
from nexus.assessment.schemas.enums import Logic, Phase, Severity
from nexus.assessment.schemas.rule import AssessmentRule
from nexus.assessment.schemas.scope import CrossTableScope, TableScope
from nexus.capture.models import ConfigRecord

__all__ = ["evaluate"]


def evaluate(rules: tuple[AssessmentRule, ...], ctx: GateContext) -> tuple[Finding, ...]:
    """Evaluate rules against ctx.capture; return findings in input order.

    Args:
        rules: AssessmentRules to evaluate.
        ctx: GateContext carrying CaptureResult, optional ApplyResult, phase.

    Returns:
        Tuple of Finding instances. Empty when every rule passed (or every
        rule was filtered out by phase mismatch).
    """
    findings: list[Finding] = []
    by_table = ctx.capture.by_table()
    captured_tables = frozenset(by_table.keys())

    for rule in rules:
        if rule.phase is not ctx.phase:
            continue
        missing = tuple(t for t in rule.required_tables if t not in captured_tables)
        if missing:
            findings.append(_completeness_finding(rule, missing, ctx.phase))
            continue
        records_for_rule = _records_for_scope(rule, by_table)
        finding = _evaluate_constraints(rule, records_for_rule, ctx.phase)
        if finding is not None:
            findings.append(finding)
    return tuple(findings)


def _completeness_finding(rule: AssessmentRule, missing: tuple[str, ...], phase: Phase) -> Finding:
    """Build the ERROR Finding emitted when required tables are missing."""
    return Finding(
        rule_id=rule.id,
        severity=Severity.ERROR,
        message=(f"required table(s) not in capture: " f"{', '.join(repr(t) for t in missing)}"),
        affected_sys_ids=(),
        phase=phase,
    )


def _records_for_scope(
    rule: AssessmentRule, by_table: dict[str, tuple[ConfigRecord, ...]]
) -> tuple[ConfigRecord, ...]:
    """Return the record slice each constraint of `rule` should see."""
    match rule.scope:
        case TableScope():
            return by_table.get(rule.scope.table, ())
        case CrossTableScope():
            joined: list[ConfigRecord] = []
            for records in by_table.values():
                joined.extend(records)
            return tuple(joined)
        case _:  # pragma: no cover -- exhaustive over RuleScope discriminator
            raise AssertionError(f"unreachable scope variant: {rule.scope!r}")


def _evaluate_constraints(
    rule: AssessmentRule, records: tuple[ConfigRecord, ...], phase: Phase
) -> Finding | None:
    """Apply rule.logic to constraint results; return Finding on failure."""
    results = tuple(constraint.evaluate(records) for constraint in rule.constraints)
    match rule.logic:
        case Logic.AND_ALL:
            return _and_finding(rule, results, phase)
        case Logic.OR_ANY:
            return _or_finding(rule, results, phase)
        case _:  # pragma: no cover -- exhaustive over Logic enum
            raise AssertionError(f"unreachable logic variant: {rule.logic!r}")


def _and_finding(
    rule: AssessmentRule, results: tuple[ConstraintResult, ...], phase: Phase
) -> Finding | None:
    """AND_ALL: pass iff every constraint passed."""
    failed = tuple(r for r in results if not r.passed)
    if not failed:
        return None
    return Finding(
        rule_id=rule.id,
        severity=rule.severity,
        message="; ".join(r.message for r in failed),
        affected_sys_ids=_merge_ids(r.affected_sys_ids for r in failed),
        phase=phase,
    )


def _or_finding(
    rule: AssessmentRule, results: tuple[ConstraintResult, ...], phase: Phase
) -> Finding | None:
    """OR_ANY: pass iff any constraint passed."""
    if any(r.passed for r in results):
        return None
    return Finding(
        rule_id=rule.id,
        severity=rule.severity,
        message="OR_ANY: " + " | ".join(r.message for r in results),
        affected_sys_ids=_merge_ids(r.affected_sys_ids for r in results),
        phase=phase,
    )


def _merge_ids(id_tuples: Iterable[tuple[str, ...]]) -> tuple[str, ...]:
    """Union sys_id tuples preserving first-seen order."""
    seen: dict[str, None] = {}
    for ids in id_tuples:
        for sys_id in ids:
            seen.setdefault(sys_id, None)
    return tuple(seen)
