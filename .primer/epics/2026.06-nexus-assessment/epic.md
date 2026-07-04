# Epic: NEXUS Assessment -- RuleEngine + Gates + `nexus assess`

Phase: 2026.06
Date: 2026-05-19
Source: .primer/prd/PRD-002-nexus-assessment.md, .primer/brainstorming/2026-05-19-nexus-assessment-rule-engine.md

## Goal

Ship the assessment subsystem: declarative YAML rules in
`templates/assessments/`, a pure RuleEngine that consumes
CaptureResult, three Gate implementations (Gate1Readiness,
Gate2Validation, HealthScan) sharing a uniform GateContext, and
a `nexus assess` CLI that exposes all three modes. Out of scope
for this epic: `nexus apply` orchestration wiring, which ships in
the Template Library epic (2026.06-template-library) once
ApplyEngine exists.

## Requirements Inventory

### Functional Requirements

* FR1: Declarative YAML rule schema (`Ruleset`, `AssessmentRule`,
  `RuleConstraint`, `RuleScope`) with author-declared
  `required_tables`, `phase`, `logic`, and `applies_to`.
  [Source: PRD-002#In Scope, brainstorm#Recommendation 1]
* FR2: Constraint DSL with 5 operators: `record_exists`,
  `field_equals`, `field_in`, `count_gte`, `count_lte`.
  [Source: PRD-002#In Scope, brainstorm#Recommendation 2]
* FR3: `RuleEngine.evaluate(rules, ctx) -> tuple[Finding, ...]` pure
  function with capture-completeness pre-check + phase-match check
  + scope dispatch + AND_ALL / OR_ANY composition.
  [Source: PRD-002#In Scope, brainstorm#Recommendation 3]
* FR4: `GateContext`, `GateReport`, three-valued `GateVerdict`,
  `GateProtocol` + three implementations (Gate1Readiness,
  Gate2Validation, HealthScan).
  [Source: PRD-002#In Scope, brainstorm#Recommendation 4]
* FR5: `AssessmentReporter.render(report, render_context)` reuses
  existing `ui/components/` (DataTable, KeyValuePanel,
  StatusBadge, Notice). No new UI primitives.
  [Source: PRD-002#In Scope, brainstorm#Recommendation 7]
* FR6: `nexus assess` CLI with three modes (`--for`, `--job`, no
  flag) and `--live` / `--archive` source switch.
  [Source: PRD-002#In Scope, brainstorm#Recommendation 5]
* FR7: At least 3 example rulesets in `templates/assessments/`
  exercising the 5-operator DSL; CI validator integration
  (`validate-templates.yml`) enforces schema validity and
  `applies_to` resolution.
  [Source: PRD-002#In Scope, brainstorm#Recommendation 8]

### Non-Functional Requirements

* NFR1: 100% line coverage on every new module.
  [Source: governance.md, CLAUDE.md]
* NFR2: pyright strict + mypy strict report 0 errors. No
  `# type: ignore`. [Source: ADR-007, ADR-012]
* NFR3: All Pydantic models frozen + strict + extra=forbid.
  [Source: ADR-021, patterns.md]
* NFR4: File-size caps -- src/ 800 LOC, tests/ 1400 LOC.
  [Source: ADR-023]
* NFR5: No mocks. Use fakes in `tests/fakes/`.
  [Source: governance.md, CLAUDE.md]

### Constraints

* C1: Layer order -- `assessment` imports from `capture`,
  `connectors`, `config`, never from `cli` or `agents`.
  [Source: patterns.md#layer-order]
* C2: Python 3.14 syntax (PEP 758 unparenthesized multi-except,
  PEP 695 type parameters, match/case with `case _:` default).
  [Source: CLAUDE.md, ADR-006]
* C3: ASCII only. UTC datetime via `from datetime import UTC`.
  [Source: global rules]

## Coverage Map

| Requirement | Story | Status |
|---|---|---|
| FR1 | 01-rule-schemas-and-yaml-loader | done |
| FR2 | 02-constraint-dsl-operators | done |
| FR3 | 03-rule-engine | done |
| FR4 | 04-gates | done |
| FR5 | 05-assessment-reporter | done |
| FR6 | 06-nexus-assess-cli | done |
| FR7 | 07-example-rulesets-and-ci | done |
| NFR1-5 | all stories | backlog |
| C1-3 | all stories | backlog |

## Story List

| # | Title | Dependencies | Status |
|---|---|---|---|
| 01 | rule-schemas-and-yaml-loader | none | done |
| 02 | constraint-dsl-operators | 01 | done |
| 03 | rule-engine | 02 | done |
| 04 | gates | 03 | done |
| 05 | assessment-reporter | 04 | done |
| 06 | nexus-assess-cli | 04 | done |
| 07 | example-rulesets-and-ci | 01 | done |

## Progress

Stories: 7/7 done -- COMPLETE

## Out of Scope (this epic)

* **`nexus apply` orchestration wiring** -- Gate 1 + Gate 2 are
  callable in isolation through `nexus assess`. Pre-apply hard
  gate orchestration ships in the Template Library epic
  (2026.06-template-library) after `ApplyEngine` lands.
* **Auto-remediation (`--fix`)** -- explicitly out of scope per
  PRD-002 anti-creep fence.
* **Nested boolean composition** -- flat AND_ALL / OR_ANY only.
* **`referenced_by_count_gte` and `parent_exists` operators** --
  defer until capture layer supports reverse references.
* **Capture-layer changes** -- this epic depends on the existing
  `CaptureResult` contract; no capture modifications.
* **MCP integration inside rules** -- rules consume CaptureResult
  only.

## References

* PRD: `.primer/prd/PRD-002-nexus-assessment.md`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-assessment-rule-engine.md`
* ADR: `.primer/adr/ADR-003-assessment-3-gate-model.md`
* Roadmap: `.primer/roadmap.md` -- 2026.06 Assessment phase
* Existing scaffolding: `src/nexus/assessment/`
* Existing capture: `src/nexus/capture/`
* Existing UI components: `src/nexus/ui/components/`
* Existing CI pattern: `.github/workflows/validate-templates.yml`
