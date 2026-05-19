# Epic: NEXUS Template Library -- ApplyEngine + Skill/Workflow schemas + 3 templates

Phase: 2026.06
Date: 2026-05-19
Source: .primer/prd/PRD-003-nexus-template-library.md, .primer/brainstorming/2026-05-19-nexus-template-library.md

## Goal

Ship the template-application subsystem: NowAssistSkill + Workflow
Pydantic schemas mapping to ai_skill / sys_hub_flow tables, an
ApplyEngine that renders templates into update-set bundles via the
shipped UpdateSetWriter, a `nexus apply <template>` CLI orchestrator
that wires Gate 1 + ApplyEngine + Gate 2, plus 3 community templates
demonstrating the v1 surface.

## Requirements Inventory

### Functional Requirements

* FR1: NowAssistSkill Pydantic schema (frozen+strict+extra=forbid)
  mapping to ai_skill table with `{{ env.X }}` field validators.
  [Source: PRD-003#In Scope, brainstorm#Recommendation 1]
* FR2: Workflow Pydantic schema mapping to sys_hub_flow + child
  tables, with nested models for inputs and logic.
  [Source: PRD-003#In Scope, brainstorm#Recommendation 2]
* FR3: TemplateDocument discriminated union (`kind`) and a YAML
  load helper following the loader pattern from Assessment.
  [Source: PRD-003#In Scope, brainstorm#Recommendation 3]
* FR4: `render_to_records(doc, scope_sys_id)` pure function -- one
  Skill -> one record; one Workflow -> parent + N children.
  [Source: PRD-003#In Scope, brainstorm#Recommendation 4]
* FR5: ApplyEngine + ApplyResult + AppliedRecord. Composes load,
  scope resolution, render, sys_update_set creation, UpdateSetWriter
  push, local apply.jsonl. Replaces Assessment's empty placeholder.
  [Source: PRD-003#In Scope, brainstorm#Recommendation 5]
* FR6: `nexus apply <id> [--scope X] [--force] [--skip-gate2]`
  orchestrator wiring Gate 1 + ApplyEngine + Gate 2 with verdict-to-
  exit mapping (PASS=0, BLOCK=2, ERROR=1).
  [Source: PRD-003#In Scope, brainstorm#Recommendation 7]
* FR7: 3 example templates + 3 per-template readiness rulesets +
  CI template-document validator + manifest.json refresh.
  [Source: PRD-003#In Scope, brainstorm#Recommendations 8-10]

### Non-Functional Requirements

* NFR1: 100% line coverage on every new module. [Source: governance.md]
* NFR2: pyright strict + mypy strict 0 errors. No `# type: ignore`.
  [Source: ADR-007, ADR-012]
* NFR3: Pydantic frozen+strict+extra=forbid. [Source: ADR-021]
* NFR4: File-size caps -- src/ 800, tests/ 1400. [Source: ADR-023]
* NFR5: No mocks; fakes only in `tests/fakes/`.
  [Source: governance.md]

### Constraints

* C1: Layer order -- templates can import capture, connectors,
  knowledge, cache. NOT agents, assessment, cli (those are higher
  layers). The `nexus apply` orchestrator lives in `src/nexus/cli/`
  and is the only place that crosses layers up to assessment.
  [Source: patterns.md#layer-order]
* C2: Python 3.14 syntax (PEP 758, PEP 695, match/case with `case _:`
  default). [Source: CLAUDE.md, ADR-006]
* C3: ASCII only. UTC datetime via `from datetime import UTC`.
  [Source: global rules]

## Coverage Map

| Requirement | Story | Status |
|---|---|---|
| FR1 | 01-now-assist-skill-schema | backlog |
| FR2 | 02-workflow-schema | backlog |
| FR3 | 03-template-document-and-loader | backlog |
| FR4 | 04-render-to-records | backlog |
| FR5 | 05-apply-engine | backlog |
| FR6 | 06-nexus-apply-cli | backlog |
| FR7 | 07-example-templates-and-ci | backlog |
| NFR1-5 | all stories | backlog |
| C1-3 | all stories | backlog |

## Story List

| # | Title | Dependencies | Status |
|---|---|---|---|
| 01 | now-assist-skill-schema | none | backlog |
| 02 | workflow-schema | none | backlog |
| 03 | template-document-and-loader | 01, 02 | backlog |
| 04 | render-to-records | 03 | backlog |
| 05 | apply-engine | 04 | backlog |
| 06 | nexus-apply-cli | 05 | backlog |
| 07 | example-templates-and-ci | 03 | backlog |

## Progress

Stories: 0/7 done, 0 in-progress, 7 backlog

## Out of Scope (this epic)

* Other 4 schemas (ai_agent, catalog_item, recipe, project) --
  stays as 1-line stubs.
* Jinja2 / general string templating beyond `{{ env.X }}`.
* Rollback engine.
* Multi-instance apply (one apply, one instance).
* Multi-step orchestration (Planner / Dispatcher).
* Cross-template dependencies.
* `--dry-run` flag (stays NotImplementedError).
* Per-record post-state verification (Gate 2's job).
* `--force` past Gate 1 ERROR (only BLOCK can be forced).
* WARNED tier in AppliedRecord (REQUESTED | FAILED only in v1).

## References

* PRD: `.primer/prd/PRD-003-nexus-template-library.md`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-template-library.md`
* ADR: `.primer/adr/ADR-002-template-github-sync.md`
* ADR: `.primer/adr/ADR-003-assessment-3-gate-model.md`
* Roadmap: `.primer/roadmap.md` -- 2026.06 Template Library phase
* Existing scaffolding: `src/nexus/templates/` (sync v1 shipped;
  schema stubs awaiting implementation)
* Sibling shipped epic: `.primer/epics/2026.06-nexus-assessment/`
* CLI stub: `src/nexus/cli/commands_top.py:152`
