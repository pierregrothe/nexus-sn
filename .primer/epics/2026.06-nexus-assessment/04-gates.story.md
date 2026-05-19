# Story 04: GateContext + GateReport + GateProtocol + 3 implementations

Status: backlog
Spec-Clarity: high
Depends-On: 03

## Story

As `nexus assess` (and later `nexus apply`),
I want a uniform GateProtocol with three implementations -- one
for each assessment mode -- that share a common GateContext and
return a common GateReport,
so that I can drive the three gates with one code path.

## Acceptance Criteria

AC1 (GateContext model):
**Given** `src/nexus/assessment/context.py`
**When** loaded
**Then** it exports `GateContext` -- Pydantic frozen+strict
+extra=forbid with fields: `capture: CaptureResult`,
`apply_result: ApplyResult | None`, `phase: Phase`.
For now `ApplyResult` is a placeholder Pydantic model
`ApplyResult(BaseModel)` with no fields (Template Library epic
will populate it).

AC2 (GateVerdict enum):
**Given** `src/nexus/assessment/verdict.py`
**When** loaded
**Then** it exports `GateVerdict = PASS | BLOCK | ERROR`
as a `StrEnum`.

AC3 (GateReport model):
**Given** `src/nexus/assessment/report.py`
**When** loaded
**Then** it exports `GateReport` -- frozen+strict+extra=forbid
with fields: `verdict: GateVerdict`,
`findings: tuple[Finding, ...]`, `summary: GateSummary`,
`ruleset_id: str | None`,
`template_id: str | None`.
`GateSummary` is a sibling model with fields:
`rules_evaluated: int`, `rules_passed: int`,
`rules_failed: int`, `rules_errored: int`,
`affected_records: int`.

AC4 (verdict derivation rules):
**Given** a `GateReport.from_findings(findings, ruleset_id,
template_id) -> GateReport` factory classmethod
**When** called
**Then** verdict is derived:
- ANY finding with `severity=ERROR` -> `verdict=ERROR`
- otherwise ANY finding with `severity=WARNING` AND from a
  rule whose context phase is PRE_APPLY -> `verdict=BLOCK`
- otherwise -> `verdict=PASS`
INFO-only findings -> `verdict=PASS` regardless.

AC5 (GateProtocol):
**Given** `src/nexus/assessment/gate.py`
**When** loaded
**Then** it exports `GateProtocol(Protocol)` with
`@runtime_checkable` decorator and one method:
`evaluate(self, ctx: GateContext) -> GateReport`.

AC6 (Gate1Readiness):
**Given** `src/nexus/assessment/gates/readiness.py`
**When** instantiated with
`Gate1Readiness(ruleset: Ruleset, template_id: str)` and
`gate.evaluate(ctx)` is called with `ctx.phase=PRE_APPLY`
**Then** it filters `ruleset.rules` to those with
`phase=PRE_APPLY`, calls `engine.evaluate(filtered_rules, ctx)`,
and returns `GateReport.from_findings(findings,
ruleset_id=ruleset.id, template_id=template_id)`.

AC7 (Gate1Readiness phase mismatch ERROR):
**Given** `Gate1Readiness` evaluated with `ctx.phase != PRE_APPLY`
**When** called
**Then** returns `GateReport(verdict=GateVerdict.ERROR, ...,
findings=(Finding(severity=ERROR, message="Gate1Readiness
requires ctx.phase=PRE_APPLY", ...),))`.

AC8 (Gate2Validation):
**Given** `src/nexus/assessment/gates/validation.py`
**When** instantiated with
`Gate2Validation(ruleset, template_id)` and
`gate.evaluate(ctx)` is called with `ctx.phase=POST_APPLY`
**Then** it filters to `phase=POST_APPLY` rules and follows the
same pattern as AC6.

AC9 (Gate2Validation requires apply_result):
**Given** `Gate2Validation.evaluate(ctx)` with
`ctx.apply_result is None`
**When** called
**Then** returns ERROR verdict with Finding message "Gate2
requires apply_result; got None". No rules evaluated.

AC10 (HealthScan):
**Given** `src/nexus/assessment/gates/health.py`
**When** instantiated with `HealthScan(ruleset)` (no template_id)
and `gate.evaluate(ctx)` is called with `ctx.phase=STANDALONE`
**Then** it filters to `phase=STANDALONE` rules and follows the
same pattern. `GateReport.template_id=None`.

AC11 (runtime_checkable protocol):
**Given** instances of Gate1Readiness, Gate2Validation,
HealthScan
**When** `isinstance(g, GateProtocol)` is checked at runtime
**Then** returns `True` for all three.

AC12 (FakeGate in tests/fakes/):
**Given** the test surface needs a recording impl
**When** Story 04 ships
**Then** `tests/fakes/gates.py` exposes `FakeGate` -- a recording
GateProtocol impl that captures `evaluated_ctxs: tuple[GateContext, ...]`
and returns a configurable `GateReport`.

## Must NOT

* Must NOT add I/O inside any gate. Engine is pure; gates only
  filter rules and wrap.
* Must NOT inline `engine.evaluate` logic -- gates delegate.
* Must NOT import from `nexus.cli` or `nexus.ui`.
* Must NOT couple to a concrete `ApplyResult` shape beyond
  `apply_result is None` checks; Template Library epic owns the
  fields.
* Must NOT make `GateReport` mutable (frozen).

## Tasks / Subtasks

* [ ] Extend `src/nexus/assessment/context.py` with final
      GateContext from Story 03 + ApplyResult placeholder (AC1)
* [ ] Create `src/nexus/assessment/verdict.py` (AC2)
* [ ] Create `src/nexus/assessment/report.py` -- GateReport,
      GateSummary, `from_findings` classmethod (AC3, AC4)
* [ ] Create `src/nexus/assessment/gate.py` -- GateProtocol (AC5)
* [ ] Create `src/nexus/assessment/gates/__init__.py`
* [ ] Create `src/nexus/assessment/gates/readiness.py` (AC6, AC7)
* [ ] Create `src/nexus/assessment/gates/validation.py` (AC8, AC9)
* [ ] Create `src/nexus/assessment/gates/health.py` (AC10)
* [ ] Create `tests/fakes/gates.py` -- FakeGate (AC12)
* [ ] Create `tests/test_gate_report.py` (AC3, AC4)
* [ ] Create `tests/test_gate_protocol.py` (AC5, AC11)
* [ ] Create `tests/test_gate1_readiness.py` (AC6, AC7)
* [ ] Create `tests/test_gate2_validation.py` (AC8, AC9)
* [ ] Create `tests/test_gate_health.py` (AC10)
* [ ] Update ratchet baselines

## Existing Code

* Story 03: `engine.evaluate`, `Finding`, `Phase`, minimal
  `GateContext` stub.
* `src/nexus/capture/models.py:CaptureResult` -- input.
* `tests/fakes/rulesets.py`, `tests/fakes/captures.py` -- fixtures.

## Dev Notes

### Modules Affected

* `src/nexus/assessment/{context.py, verdict.py, report.py, gate.py}`
* `src/nexus/assessment/gates/{__init__.py, readiness.py, validation.py, health.py}`
* `tests/fakes/gates.py`
* `tests/test_gate_*.py` (5 files)

### Testing Approach

* Each Gate has its own test file. One AC -> one test method.
* Tests construct real Ruleset + real CaptureResult fixtures
  via fakes. No mocks.
* `FakeGate` reused by downstream stories (05 reporter, 06 CLI).
* Coverage: 100% on every gate module.

### Conventions

* `@dataclass(slots=True)` for Gate implementations (not Pydantic
  -- they hold protocol-bound mutable references like `ruleset`
  and `template_id` is enough)
* OR: Pydantic frozen with `Field(exclude=True)` for the protocol
  side. Pick whichever passes pyright strict cleanly.
* `match`/`case` over `Phase` and `GateVerdict` with `case _:`

### Verdict derivation table (AC4 reference)

| Findings | ctx.phase | Verdict |
|---|---|---|
| any ERROR | * | ERROR |
| any WARNING, no ERROR | PRE_APPLY | BLOCK |
| any WARNING, no ERROR | POST_APPLY or STANDALONE | PASS (warning observed but not blocking) |
| only INFO | * | PASS |
| none | * | PASS |

(Rationale: WARNING is advisory in post-apply / standalone but
blocking pre-apply. ERROR is always BLOCK-equivalent but called
ERROR to distinguish "we couldn't evaluate" vs "we found a
failure".)

## References

* Stories 01, 02, 03
* PRD: `.primer/prd/PRD-002-nexus-assessment.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-assessment-rule-engine.md#Recommendation 4`
* ADR: `.primer/adr/ADR-003-assessment-3-gate-model.md`
