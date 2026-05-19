# Brainstorming: NEXUS Assessment Epic -- RuleEngine + Gates + `nexus assess`

Date: 2026-05-19
Mode: assumptions
Techniques: assumptions-mode (researcher brief -> Unclear-item confirmation -> 2x adversarial pass)

## Context Brief

Project: NEXUS Python 3.14 ServiceNow architect CLI. Next planned
phase: 2026.06 Assessment (RuleEngine + AssessmentReporter +
`nexus assess` + Gates 1/2).

What exists today (Confident, verified):
* `nexus.capture` layer shipped: `CaptureResult` (frozen+strict,
  `tuple[ConfigRecord, ...]`, `by_table()` grouping), ArchiveWriter/Reader
  (YAML), CaptureEngine. (`src/nexus/capture/models.py:78-88`)
* `nexus.assessment/` package exists as scaffolding only -- stub
  modules `scanner.py`, `readiness.py`, `reporter.py`, `validator.py`,
  `rules.py` (2-line stub) and three schema stubs.
* `nexus assess` CLI registered (`src/nexus/cli/commands_top.py:132-148`)
  with `--for` (Gate 1) and `--job` (Gate 2) -- raises NotImplementedError.
* ADR-003 defines the 3-gate model: Gate 1 = pre-deploy readiness;
  Gate 2 = post-deploy validation; standalone = `nexus assess` health.
* Plugins layer has rule-engine-like `_check_*()` patterns
  (`src/nexus/plugins/advisories.py:79-119`) returning typed
  `tuple[Finding, ...]` -- imperative Python, not YAML.
* CI pattern for YAML+Pydantic exists (`validate-templates.yml`).

Confirmed assumptions (Unclear items resolved with user):
* Rule authorship: **YAML rulesets** in `templates/assessments/`
  (not Python `_check_*()` functions)
* Gate 1 failure semantics: **hard block** (exit-2 + `--force` escape)
* RuleEngine input: **scope-routed** (rule declares `scope:`,
  engine dispatches by rule)
* `nexus assess` source: **archive default, `--live` flag** to re-capture
* `nexus apply` integration: **pre-apply hard gate** -- capture-live,
  Gate 1, apply, recapture, Gate 2

Hard project constraints:
* Pydantic frozen+strict+extra=forbid
* Python 3.14 syntax (PEP 758, PEP 695, match/case)
* No mocks (fakes only, `tests/fakes/`)
* File-size caps ADR-023: src/ 800, tests/ 1400
* 100% line coverage, mypy strict, pyright strict, ruff 0
* Layer order: capture/connectors -> assessment -> cli

## Key Insights

1. **YAML rules + Python interpreter is the load-bearing piece**, and
   bigger than `_check_*()`-style imperative rules. We need: Pydantic
   `AssessmentRule` schema, a declarative constraint DSL with
   discriminated-union operators, a YAML loader with CI validation
   mirroring `validate-templates.yml`, and a dispatcher that routes
   rules to their scoped slice of `CaptureResult`. This is the largest
   single design surface in the epic.

2. **Gates are a thin layer above RuleEngine**, not parallel to it.
   `Gate1Readiness`, `Gate2Validation`, and `HealthScan` differ only
   in which ruleset they load and which `GateContext` they receive.
   One protocol; three call sites.

3. **`nexus assess --live` vs `--archive` is a CLI routing concern**,
   not engine concern. RuleEngine always takes a `CaptureResult`.
   CLI resolves which one (live = invoke CaptureEngine; archive =
   ArchiveReader). Engine stays pure and reusable from both `assess`
   and `apply`.

4. **Pre-apply hard gate creates a tight orchestrator boundary.**
   `nexus apply <template>` = capture-live -> Gate 1 -> apply ->
   recapture-live -> Gate 2 -> final GateReport. `--force` escapes
   Gate 1 verdict only; capture and Gate 2 always run.

5. **Rules declare dispatch scope in YAML** (`scope: table: X` or
   `scope: cross-table`). RuleEngine routes accordingly. Author
   declares `required_tables: tuple[str, ...]` explicitly; engine
   validates capture coverage before evaluating -- no silent false
   PASS when capture is incomplete.

6. **Verdict is three-valued: PASS | BLOCK | ERROR.** ERROR is
   distinct from BLOCK -- "we couldn't evaluate" (capture failed,
   rule load failed, schema invalid) is a different exit path than
   "we evaluated and found a failure."

7. **AND/OR composition is flat in v1**, not nested. Each rule has
   `logic: Logic = AND_ALL | OR_ANY` over a flat `constraints`
   tuple. Nested boolean trees are out of scope; they cover <5%
   of real readiness scenarios and force a much larger DSL surface.

## Recommendations (build sequence)

1. **Rule schema + YAML loader** (foundation). Pydantic
   `AssessmentRule`, `Ruleset`, `RuleScope`, `RuleConstraint`
   frozen+strict+extra=forbid. Discriminated union per scope -- a
   `count_lte` constraint against a `table` scope is a different
   pydantic variant than against a `cross-table` scope. Schema
   validator enforces `every constraint.table in
   AssessmentRule.required_tables`. CI mirrors `validate-templates.yml`
   to validate every `templates/assessments/*.yaml` on PR.

2. **Constraint DSL: 5-operator initial set.**
   * `record_exists` (filter -> at least one record matches)
   * `field_equals` (record -> field == expected)
   * `field_in` (record -> field in expected_set)
   * `count_gte` (filter -> count >= N)
   * `count_lte` (filter -> count <= N)

   Defer `referenced_by_count_gte` (requires capture-layer reverse
   refs). Defer `parent_exists` (rarely needed; `record_exists` with
   filter on parent_sys_id covers most cases). Defer nested boolean
   composition.

3. **RuleEngine.evaluate(rules, ctx) -> tuple[Finding, ...] pure
   function.** Steps:
   a. Validate `ctx.capture.tables() >= union(rule.required_tables
      for rule in rules)`; missing tables -> ERROR finding per
      affected rule.
   b. Validate `rule.phase` matches `ctx.phase` (PRE_APPLY in Gate 1
      context; POST_APPLY in Gate 2 context). Mismatch -> skip with
      info finding.
   c. Dispatch each rule by `scope`; route slice of `CaptureResult`.
   d. Evaluate constraints under `rule.logic`; emit Finding on
      failure with affected sys_ids.

4. **GateProtocol + 3 implementations.**
   ```
   class GateContext(BaseModel):
       capture: CaptureResult
       apply_result: ApplyResult | None
       phase: GatePhase  # PRE_APPLY | POST_APPLY | STANDALONE

   class GateReport(BaseModel):
       verdict: GateVerdict  # PASS | BLOCK | ERROR
       findings: tuple[Finding, ...]
       summary: GateSummary

   class GateProtocol(Protocol):
       def evaluate(self, ctx: GateContext, template_id: str | None) -> GateReport: ...
   ```
   `Gate1Readiness`, `Gate2Validation`, `HealthScan` are three
   subclasses (or @dataclass(slots=True) implementations) each
   loading their ruleset slug and calling the shared engine.

5. **`nexus assess` CLI surface.**
   * `nexus assess --for <template> [--live|--archive PATH]` -> Gate 1
   * `nexus assess --job <apply-job-id> [--live]` -> Gate 2 (reads
     apply log to reconstruct `ApplyResult`, recaptures by default)
   * `nexus assess [--live|--archive PATH]` -> HealthScan
   * Default = `--archive` (use most recent `nexus capture` output)

6. **`nexus apply` orchestration** (hardened from adversarial v2):
   ```
   capture_live_against_target_scope()
   gate1 = Gate1Readiness().evaluate(ctx1, template_id)
   if gate1.verdict is BLOCK and not force:
       exit 2 with --force hint
   apply_result = ApplyEngine.apply(template, ...)
   recapture = capture_live_against_target_scope()  # always, unless --skip-gate2
   gate2 = Gate2Validation().evaluate(ctx2, template_id)
   if gate2.verdict is ERROR:
       exit 1 with "verification incomplete" notice
   print final GateReport
   ```
   `--force` only skips Gate 1 verdict, never capture or Gate 2.
   `--skip-gate2` flag exists (advisory; off by default; documented as
   "skip post-apply verification").

7. **AssessmentReporter -- reuse existing ui/components/.** Build
   `report_to_console(report: GateReport, render_context: RenderContext)`
   using `DataTable` (findings list), `KeyValuePanel` (summary),
   `StatusBadge` (verdict), `Notice` (header + remediation hints).
   No `FramedViewer` (assessment output isn't paginated tables).
   No new UI surface. Mirrors `nexus plugins advisories` rendering.

8. **CI validator additions.**
   * `templates/assessments/*.yaml` parsed by `Ruleset` Pydantic
     schema in PR workflow.
   * Every `Ruleset.applies_to` entry must resolve to an existing
     `templates/<id>/manifest.yaml`. Catch stale references on
     template rename.

## Trade-offs

| Option | Pro | Con | Position |
|---|---|---|---|
| YAML DSL min set (5 ops) | Ships fast; covers most readiness cases | Cannot express complex business rules | Pick min set; extend by adding operators per story |
| YAML DSL rich set (20+ ops) | Future-proof | Months of design; speculative | Reject (YAGNI) |
| Discriminated-union constraints | Pydantic-validated; type-safe | More verbose | Pick |
| Free-form `expression: "field == X"` strings | Concise | Eval surface; injection risk; untyped | Reject |
| Gate 1 hard-block exit 2 | Matches typer + InteractiveRequiredError precedent | Same code as usage error | Pick; `--force` is the escape |
| Mandatory post-apply recapture | Gate 2 sees real state | Adds latency to every apply | Pick; `--skip-gate2` opt-out |
| Standalone ruleset + `applies_to` | One file model; shared OR template-specific | Shared rules require union of required_tables | Pick; document the trade-off |
| Co-located ruleset (per-template) | Clear ownership | No sharing across templates | Reject (no sharing path) |
| Three-valued verdict PASS/BLOCK/ERROR | Distinguishes "rule failed" from "we couldn't evaluate" | Slightly more reporter UI work | Pick |
| Two-valued verdict PASS/BLOCK | Simpler reporter | Capture failure looks like a fail finding | Reject |
| Flat AND_ALL/OR_ANY composition | Simpler DSL; covers 95% of cases | Cannot express XOR or nested trees | Pick; nesting deferred |
| Author-declared `required_tables` | Explicit; schema-validated | One more field per rule | Pick; engine-inferred is brittle for joins |

## Out of Scope (explicit anti-creep fence)

* Rule authoring UI / web editor -- YAML hand-edited or generated.
* Auto-remediation (`nexus assess --fix`) -- gates report; never act.
  `--force` is "I accept the risk"; `--fix` would be "act on findings."
  Different verbs; reject `--fix`.
* Runtime Python rule plugins -- rules ship as YAML in
  `templates/assessments/`. New operators require code PR + ADR.
* Assessment history / time-series -- gates evaluate now; archive
  layer owns before/after.
* Cross-instance comparison -- one capture, one assessment.
* Rule marketplace beyond the existing GitHubSync registry.
* Live ServiceNow MCP queries inside rules -- rules consume
  `CaptureResult`. MCP integration is the Agent Specialists epic.
* Scoring / weighting -- verdict is PASS/BLOCK/ERROR. No aggregate
  scores in v1.
* Nested boolean composition (XOR, NOT, nested AND/OR) -- flat
  AND_ALL / OR_ANY only.
* Capture-layer reverse-reference fetching -- defers
  `referenced_by_count_gte` until capture supports it.
* `nexus apply` SLA bound for post-apply recapture latency --
  measure first, optimize per data.

## Open Questions

1. Beyond the 5-operator initial DSL, what's the next operator to add?
   Defer to epic decomposition. Each new operator = one story.

## Adversarial Review

Two passes. v1 found 4 BLOCKERs + 2 CONCERNs + 1 NIT:
* Gate 2 input shape (CaptureResult vs ApplyResult) breaks
  protocol uniformity -- resolved with `GateContext(capture,
  apply_result | None, phase)`.
* `--force` + Gate 2 staleness -- resolved with mandatory post-apply
  recapture.
* Ruleset location is an ownership decision, not cosmetic --
  resolved with standalone + `applies_to: tuple[template_id, ...]`.
* Cross-table rules + incomplete capture = silent false PASS --
  resolved with author-declared `required_tables` and engine
  pre-check.

v2 found 1 new BLOCKER + 5 CONCERNs:
* AND/OR constraint composition unspecified -- resolved with
  `logic: AND_ALL | OR_ANY` enum (flat only in v1).
* Gate 1 None-defensiveness -- resolved with `phase` discriminator;
  rules never inspect `apply_result`.
* `required_tables` inference vs declared -- resolved with
  author-declared + schema validation.
* Recapture failure path -- resolved with ERROR verdict + exit-1 +
  retry notice.
* `applies_to` stale references -- resolved with CI validator.
* Shared rules with divergent required_tables -- accept the union
  trade-off; document.
* Post-apply recapture latency / no opt-out -- resolved with
  `--skip-gate2` flag.

No remaining BLOCKERs at synthesis level. Story-level design
ambiguities will surface during epic decomposition.

## Research Findings Appendix

### Capture layer surface (Confident)
* `CaptureResult` Pydantic frozen+strict+extra=forbid
  (`src/nexus/capture/models.py:78-88`)
* `tuple[ConfigRecord, ...]` where `ConfigRecord` has `sys_id`,
  `table`, `scope_sys_id`, `fields: SnRecord`, `parent_sys_id`
* `by_table()` grouping method exists -- the design intent for
  per-table dispatch
* `ArchiveWriter/Reader` serialize to YAML
* Connects to: Recs 3 + 5 (engine input + assess CLI archive mode)

### Assessment scaffolding (Confident)
* `src/nexus/assessment/` -- stubs: `scanner.py`, `readiness.py`,
  `reporter.py`, `validator.py`, `rules.py` (2-line stub)
* Schema stubs: `schemas/health.py`, `schemas/readiness.py`,
  `schemas/validation.py`
* CLI: `cli/commands_top.py:132-148` -- `nexus assess` registered;
  raises `NotImplementedError`
* Connects to: every recommendation -- the scaffolding is the build target

### ADR-003 gate model (Confident)
* `.primer/adr/ADR-003-assessment-3-gate-model.md`
* Gate 1 = pre-deploy readiness; Gate 2 = post-deploy validation;
  standalone = health
* Each gate is stateless `RuleEngine` evaluation
* Assessment layer only reports; execution owns rollback
* Connects to: Rec 4 (GateProtocol)

### Plugins layer rule-engine patterns (Likely)
* `src/nexus/plugins/advisories.py:79-119` -- `_check_eol`,
  `_check_cves`, `_check_license` consume domain models, return
  typed `tuple[AdvisoryFinding, ...]`
* `Finding` models are Pydantic frozen with severity enum, message,
  affected sys_ids
* No `Protocol` abstraction yet -- each plugins sub-project is
  a self-contained module
* Connects to: Rec 2 (DSL output maps to typed Finding) and Rec 7
  (reporter mirrors plugins UI)

### Template CI pattern (Confident)
* `.github/workflows/validate-templates.yml` validates `templates/**.yaml`
  against Pydantic schemas on PR
* Pattern: schema in `src/nexus/templates/schemas/`, YAML in
  `templates/`, CI runs Pydantic parse
* Connects to: Rec 1 + Rec 8 (mirror for `templates/assessments/`)

### File-size constraints (Confident)
* ADR-023: src/ 800 LOC, tests/ 1400 LOC
* RuleEngine + DSL likely needs splitting:
  `engine.py`, `constraints.py`, `loader.py`, `gates.py`, `reporter.py`,
  `schemas/rule.py`, `schemas/ruleset.py`
* Plus per-Gate modules: `gate_readiness.py`, `gate_validation.py`,
  `health_scan.py`
* Connects to: epic decomposition story count (likely 7-9 stories)

## Session Notes

### Round 1: Researcher brief

Returned in ~90 seconds. Six Confident findings (capture shape, scaffolding,
gates, plugins patterns, CLI, layer order). Three Likely findings
(reuse plugins finding model, Pydantic schemas, fake-based tests).
Five Unclear items elevated to user.

### Round 2: User confirmation of Unclear items

All five Unclear items resolved:
* Rules in YAML (not Python)
* Gate 1 hard block (exit 2 + --force)
* RuleEngine dispatches by rule-declared scope
* `nexus assess` reads archive by default, `--live` flag re-captures
* `nexus apply` pre-apply hard gate (Gate 1 -> apply -> Gate 2)

### Round 3: Adversarial v1

Flagged 4 BLOCKERs around Gate 2 input shape, --force staleness,
ruleset location ownership, capture-completeness silent-PASS. All
resolved by introducing `GateContext`, mandatory post-apply
recapture, standalone + `applies_to`, and author-declared
`required_tables`.

### Round 4: Adversarial v2

Confirmed v1 BLOCKERs closed. Found 1 new BLOCKER (AND/OR
composition) plus concerns. All resolved by adding `logic` enum,
`phase` discriminator, recapture failure -> ERROR + exit 1,
`applies_to` CI validation, accepting union trade-off for shared
rules, and `--skip-gate2` flag.
