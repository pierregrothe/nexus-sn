# Story 03: RuleEngine.evaluate -- pure function with capture-completeness + phase + dispatch

Status: done
Spec-Clarity: high
Depends-On: 02

## Story

As a Gate implementation,
I want a single `RuleEngine.evaluate(rules, ctx) ->
tuple[Finding, ...]` pure function that handles completeness
checks, phase matching, scope dispatch, and AND/OR composition,
so that all three Gates (and standalone scan) share one
evaluation core with no I/O.

## Acceptance Criteria

AC1 (Finding model):
**Given** the file `src/nexus/assessment/findings.py`
**When** loaded
**Then** it exports `Finding` -- Pydantic frozen+strict+extra=forbid
with fields: `rule_id: str`, `severity: Severity`, `message: str`,
`affected_sys_ids: tuple[str, ...]`, `phase: Phase`.

AC2 (RuleEngine.evaluate signature):
**Given** `src/nexus/assessment/engine.py`
**When** loaded
**Then** it exports `evaluate(rules: tuple[AssessmentRule, ...],
ctx: GateContext) -> tuple[Finding, ...]`. Module-level function;
no class needed.

AC3 (capture-completeness pre-check):
**Given** a rule with `required_tables = ("sys_scope", "sys_user")`
and a `GateContext` whose `capture.tables()` returns only
`("sys_scope",)`
**When** `evaluate((rule,), ctx)` runs
**Then** it returns one Finding with
`severity=Severity.ERROR`,
`message=f"required table 'sys_user' not in capture"`,
`affected_sys_ids=()`,
`phase=ctx.phase`,
`rule_id=rule.id`.
The rule's constraints are NOT evaluated.

AC4 (phase mismatch -- rule skipped, info finding):
**Given** a rule with `phase=Phase.POST_APPLY` and a
`GateContext(phase=Phase.PRE_APPLY)`
**When** `evaluate((rule,), ctx)` runs
**Then** the rule is skipped silently -- no Finding emitted
(neither error nor info). Phase mismatch is normal cross-gate
filtering, not a failure.

AC5 (table scope dispatch):
**Given** a rule with `scope=TableScope(table="sys_scope")`
**When** evaluated
**Then** each constraint receives only records where
`record.table == "sys_scope"` (filtered slice of
`ctx.capture.records`).

AC6 (cross-table scope dispatch):
**Given** a rule with `scope=CrossTableScope()`
**When** evaluated
**Then** each constraint receives the full
`ctx.capture.records` tuple.

AC7 (AND_ALL composition):
**Given** a rule with `logic=Logic.AND_ALL` and 3 constraints
where 2 pass and 1 fails
**When** evaluated
**Then** one Finding is emitted with the failed constraint's
affected_sys_ids and a message identifying it as the failing
constraint. No Findings emitted when ALL pass.

AC8 (OR_ANY composition):
**Given** a rule with `logic=Logic.OR_ANY` and 3 constraints
where 2 fail and 1 passes
**When** evaluated
**Then** NO Finding emitted. Rule passes if any constraint
passes.

AC9 (OR_ANY all-fail):
**Given** a rule with `logic=Logic.OR_ANY` and all constraints
fail
**When** evaluated
**Then** one Finding is emitted with combined message listing
each failed constraint, and `affected_sys_ids` is the union of
each constraint's affected ids.

AC10 (severity propagation):
**Given** a rule with `severity=Severity.WARNING`
**When** the rule fails
**Then** the emitted Finding has `severity=Severity.WARNING`.
Severity is per-rule, not per-constraint.

AC11 (empty rules):
**Given** `evaluate((), ctx)` with no rules
**When** called
**Then** returns `()` (empty tuple). No errors.

AC12 (multiple rules, mixed outcomes):
**Given** 3 rules where rule A passes, rule B fails with
ERROR, rule C fails with WARNING
**When** evaluated
**Then** returns a tuple of 2 Findings in input order
(B then C). Passing rules emit no Finding.

AC13 (purity):
**Given** any input
**When** evaluate runs
**Then** zero I/O. No print, no logging. No filesystem. No
network. No mutation of inputs.

AC14 (type strictness):
**Given** the new file
**When** pyright strict + mypy strict run
**Then** 0 errors. No `# type: ignore`.

## Must NOT

* Must NOT log inside evaluate. Pure function.
* Must NOT mutate `rules` or `ctx`.
* Must NOT raise on rule failure -- emit Findings instead.
* Must NOT short-circuit by returning early before scanning all
  rules (AC12 requires processing each).
* Must NOT depend on any I/O package or `nexus.cli`.

## Tasks / Subtasks

* [ ] Define `Finding` in `src/nexus/assessment/findings.py` (AC1)
* [ ] Define `evaluate(rules, ctx) -> tuple[Finding, ...]` in
      `src/nexus/assessment/engine.py` (AC2)
* [ ] Implement capture-completeness pre-check (AC3)
* [ ] Implement phase-match filter (AC4)
* [ ] Implement scope dispatch (AC5, AC6)
* [ ] Implement AND_ALL composition (AC7)
* [ ] Implement OR_ANY composition (AC8, AC9)
* [ ] Propagate rule.severity to Finding (AC10)
* [ ] Add `GateContext` placeholder to `src/nexus/assessment/context.py`
      (Story 04 fully implements; this story uses minimal
      `GateContext(capture, phase)` for tests).
* [ ] Create `tests/fakes/captures.py` -- FakeCaptureResult helpers
* [ ] Create `tests/test_rule_engine_evaluate.py` (AC2, AC11, AC12, AC13, AC14)
* [ ] Create `tests/test_rule_engine_completeness_check.py` (AC3)
* [ ] Create `tests/test_rule_engine_phase_filter.py` (AC4)
* [ ] Create `tests/test_rule_engine_scope_dispatch.py` (AC5, AC6)
* [ ] Create `tests/test_rule_engine_logic_composition.py` (AC7, AC8, AC9, AC10)
* [ ] Update ratchet baseline

## Existing Code

* Story 01: `AssessmentRule`, `Ruleset`, `RuleScope`,
  `Severity`, `Phase`, `Logic`.
* Story 02: `RuleConstraint` variants with `.evaluate(records)`.
* `src/nexus/capture/models.py:CaptureResult` -- input data.
  Has `by_table()` grouping method already.

## Dev Notes

### Modules Affected

* `src/nexus/assessment/engine.py` (new)
* `src/nexus/assessment/findings.py` (new)
* `src/nexus/assessment/context.py` (new, minimal stub)
* `tests/fakes/captures.py` (new)
* `tests/test_rule_engine_*.py` (5 test files)

### Testing Approach

* Build a `FakeCaptureResult` builder in `tests/fakes/captures.py`
  that takes `dict[table, tuple[ConfigRecord, ...]]` and produces
  a real `CaptureResult` instance (no mocking).
* Use real Ruleset/Rule/Constraint instances from
  `tests/fakes/rulesets.py` (Story 01).
* AC3 test must verify that the rule's constraints are NOT
  invoked when completeness check fails (use a constraint with a
  spy via subclass, or count side-effect-free invocations using
  a counter Constraint variant for testing).
* Coverage: 100% line on engine.py, findings.py, context.py.

### Conventions

* Pure function; no class state
* `match`/`case` over `RuleScope` discriminator
* `match`/`case` over `Logic` enum with `case _:` default
* Tests use class-based grouping `class TestRuleEngineEvaluate:`
  (project convention)

## References

* Stories 01, 02
* PRD: `.primer/prd/PRD-002-nexus-assessment.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-assessment-rule-engine.md#Recommendation 3`
* `src/nexus/capture/models.py:CaptureResult`
* ADR: `.primer/adr/ADR-003-assessment-3-gate-model.md`
