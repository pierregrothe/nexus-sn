---
id: PRD-002
title: NEXUS Assessment -- RuleEngine + Gates + nexus assess
status: draft
date: 2026-05-19
adrs: [ADR-003]
charter_link: charter.md
milestone: 2026.06-assessment
---

# PRD-002: NEXUS Assessment -- RuleEngine + Gates + `nexus assess`

## Problem

NEXUS can already capture (`nexus capture`) and act on ServiceNow
configuration (`nexus plugins ...`, `nexus apply` planned), but it
has no way to evaluate captured state against declarative
correctness rules. There is no readiness check before a template
applies, no post-deploy validation that the apply produced the
expected state, and no standalone health audit. ADR-003 defines a
3-gate model for assessment (Gate 1 readiness, Gate 2 validation,
standalone health) but the `nexus.assessment/` package is empty
scaffolding and `nexus assess` raises `NotImplementedError`. This
PRD ships the layer that closes that gap.

## Users

* Operators running `nexus apply <template>` who need the tool to
  refuse on missing prerequisites instead of half-applying and
  leaving them with broken state.
* Operators auditing existing ServiceNow instances who want a
  declarative answer to "what's wrong here?" via `nexus assess`.
* Rule authors contributing community rulesets in
  `templates/assessments/*.yaml` -- no Python required.
* CI pipelines wrapping `nexus apply` that need a hard non-zero
  exit on readiness failure to fail builds.

## In Scope (must-haves)

* **`Ruleset` + `AssessmentRule` Pydantic schemas** (frozen + strict
  + extra=forbid). Discriminated-union `RuleConstraint` per scope.
  Author-declared `required_tables: tuple[str, ...]`. Author-declared
  `phase: PRE_APPLY | POST_APPLY | STANDALONE`. Author-declared
  `logic: AND_ALL | OR_ANY` over a flat constraints tuple. Author-
  declared `applies_to: tuple[template_id, ...]` for ruleset-template
  binding.
* **YAML ruleset loader + CI validator**. `templates/assessments/*.yaml`
  parsed by `Ruleset` Pydantic schema. `applies_to` entries resolved
  against `templates/<id>/manifest.yaml`. Mirrors `validate-templates.yml`.
* **Constraint DSL v1 -- 5 operators**: `record_exists`, `field_equals`,
  `field_in`, `count_gte`, `count_lte`. Each is a Pydantic-validated
  discriminated-union variant.
* **`RuleEngine.evaluate(rules, ctx) -> tuple[Finding, ...]`** pure
  function. Validates capture coverage against `required_tables`
  before evaluating. Validates `rule.phase` matches `ctx.phase`.
  Dispatches per scope. Emits `Finding` (frozen Pydantic) with
  severity, message, affected sys_ids, source rule id.
* **`GateContext(capture, apply_result | None, phase)`** uniform
  input model. Gate 1 receives `apply_result=None`; Gate 2 always
  has both.
* **`GateReport(verdict: GateVerdict, findings, summary)`** with
  three-valued verdict: PASS, BLOCK, ERROR. ERROR is distinct from
  BLOCK -- "we couldn't evaluate" vs "we evaluated and found
  failures."
* **`GateProtocol` + three implementations**: `Gate1Readiness`,
  `Gate2Validation`, `HealthScan`. Each loads its ruleset slug and
  calls the shared engine.
* **`nexus assess` CLI** with three modes:
  - `nexus assess --for <template> [--live|--archive PATH]` -> Gate 1
  - `nexus assess --job <apply-job-id> [--live]` -> Gate 2
  - `nexus assess [--live|--archive PATH]` -> HealthScan
  - Default = `--archive` (most recent `nexus capture` output)
* **`nexus apply` pre-apply hard gate wiring**: capture-live ->
  Gate 1 -> apply -> recapture-live -> Gate 2 -> final GateReport.
  BLOCK verdict on Gate 1 -> exit-2 with `--force` hint.
  `--force` escapes Gate 1 verdict only (capture and Gate 2 still
  run). `--skip-gate2` flag for explicit opt-out of post-apply
  recapture.
* **`AssessmentReporter`** reusing existing `ui/components/`
  (`DataTable`, `KeyValuePanel`, `StatusBadge`, `Notice`). No new
  UI surface. Mirrors `nexus plugins advisories` rendering.
* **Fakes in `tests/fakes/`**: `FakeCaptureResult`, `FakeRuleset`,
  `FakeGateProtocol`. Tests use these only; no mocks.

## Out of Scope (anti-creep fence -- the load-bearing section)

* **Rule authoring UI / web editor** -- YAML hand-edited or
  generated. No interactive rule builder.
* **Auto-remediation (`nexus assess --fix`)** -- gates report; they
  never act. `--force` is "I accept the risk"; `--fix` would be
  "act on findings." Different verbs. `--fix` is rejected for v1
  and is the most likely scope-creep request.
* **Runtime Python rule plugins** -- rules ship as YAML in
  `templates/assessments/`. New constraint operators require a code
  PR + ADR. No `entry_points` or dynamic loader.
* **Assessment history / time-series** -- gates evaluate now.
  Before/after comparison lives in the capture archive layer.
* **Cross-instance comparison** -- one capture, one assessment.
* **Rule marketplace beyond the existing GitHubSync registry**.
  Community rules ship as PRs to `templates/assessments/` via the
  same flow as templates.
* **Live ServiceNow MCP queries inside rules** -- rules consume
  `CaptureResult` only. MCP integration is the Agent Specialists
  epic (2026.07).
* **Scoring / weighting** -- verdict is PASS / BLOCK / ERROR. No
  aggregate scores in v1.
* **Nested boolean composition** (XOR, NOT, nested AND/OR) -- flat
  `AND_ALL` / `OR_ANY` only in v1. Covers >95% of real readiness
  rules.
* **Capture-layer reverse-reference fetching** -- defers
  `referenced_by_count_gte` and `parent_exists` until the capture
  layer supports reverse refs.
* **`nexus apply` SLA bound for post-apply recapture latency** --
  measure first; optimize per data. `--skip-gate2` is the only
  opt-out lever.
* **Engine inference of `required_tables`** -- author declares
  explicitly; schema validates. Inference for join-style rules is
  brittle.
* **Shared rules with divergent `required_tables` per template** --
  declare the union; if a template doesn't need a captured table,
  RuleEngine still requires it captured. Authors split into per-
  template rulesets to avoid waste.

## Acceptance Criteria

- [ ] `Ruleset` + `AssessmentRule` + `RuleConstraint` Pydantic models
  in `src/nexus/assessment/schemas/` -- frozen+strict+extra=forbid;
  pyright + mypy strict 0 errors; 100% line coverage.
- [ ] `RuleEngine.evaluate(rules, ctx) -> tuple[Finding, ...]` pure
  function with no I/O; tests cover empty-capture, missing-required-
  table, phase-mismatch, AND_ALL pass + fail, OR_ANY pass + fail,
  cross-table dispatch, per-table dispatch.
- [ ] Discriminated-union constraint variants per scope; schema
  validator catches operator-scope incompatibility at YAML parse
  time (CI test covers each combination).
- [ ] `Gate1Readiness`, `Gate2Validation`, `HealthScan` all implement
  `GateProtocol`; each returns `GateReport` with three-valued
  verdict.
- [ ] `nexus assess --for <template>`, `nexus assess --job <id>`,
  `nexus assess` (no flags) all functional end-to-end against a
  `FakeCaptureResult`. Smoke test covers each path.
- [ ] `nexus apply` orchestrator runs Gate 1 -> apply -> recapture
  -> Gate 2 with verdict handling: BLOCK + no `--force` -> exit-2;
  ERROR on Gate 2 -> exit-1 with retry notice; PASS -> exit-0.
- [ ] `templates/assessments/*.yaml` validated by CI on PR; stale
  `applies_to` references caught.
- [ ] `AssessmentReporter` renders `GateReport` to console using
  existing `ui/components/` only (no new UI primitives).
- [ ] At least 3 example rulesets shipped under
  `templates/assessments/` exercising the 5-operator DSL.
- [ ] All new modules conform to ADR-023 size caps (src/ 800,
  tests/ 1400). RuleEngine + DSL likely split into 5-7 modules.

## Success Metrics

* `nexus apply` blocks at least one real readiness violation before
  causing partial-apply state (observed in dogfooding or UAT).
* `nexus assess --job <id>` catches at least one post-deploy drift
  the operator would otherwise have missed.
* Time-to-author-first-rule for a contributor with no NEXUS code
  knowledge: < 1 hour from reading the YAML example to opening a PR.
* Zero false-PASS verdicts from rules whose `required_tables` are
  unmet (engine pre-check catches all of them).

## Dependencies

* **ADR-003** -- 3-gate assessment model (existing).
* **Capture layer** -- `CaptureResult`, `ArchiveWriter/Reader`,
  `CaptureEngine` (shipped).
* **Templates layer** -- `templates/` registry for `applies_to`
  resolution (shipped).
* **UI components layer** -- `DataTable`, `KeyValuePanel`,
  `StatusBadge`, `Notice` (shipped).
* **Plugins layer** -- the `Finding` model and `_check_*()` pattern
  inform the design but are not imported. Assessment ships its own
  Finding type (different fields).
* **PluginExecutor / ApplyEngine** -- Gate 1 wires into `nexus
  apply <template>`. ApplyEngine itself is planned in the Template
  Library epic (2026.06-template-library) -- Gate 1 and Gate 2 ship
  with stubs callable in isolation until ApplyEngine lands.

## Out of Library Scope (always)

Assessment ships as part of the NEXUS CLI; there is no separate
"library." All assessment code lives under `src/nexus/assessment/`.
Runtime concerns the runtime owns:
* ServiceNow MCP probing -- the capabilities layer.
* OAuth credential refresh -- the auth layer.
* HTTP transport -- the connectors layer.
* Console rendering primitives -- the ui/components layer.

Assessment depends on but does not duplicate any of the above.

## Open Questions

* Beyond the 5-operator initial DSL, what's the next operator to
  add when the first real ruleset hits a wall? Defer until epic
  decomposition surfaces the concrete gap.
* Should `Gate2Validation` accept an explicit `expected_state`
  passed by `ApplyEngine` (in addition to `apply_result`)? Defer
  until ApplyEngine design lands.
* Format of `--job <id>` -- is the apply job id a UUID we mint, or
  the ServiceNow sys_id of the change request? Defer to story
  level.

## References

* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-assessment-rule-engine.md`
* ADR-003: 3-gate assessment model
* ADR-023: file size limits
* Roadmap: `.primer/roadmap.md` -- 2026.06 Assessment phase
* Existing scaffolding: `src/nexus/assessment/` (5 stubs + 3 schema stubs)
