# Epic: NEXUS Replatform Checklist -- `nexus assess inventory` + `nexus assess migration`

Phase: 2026.07
Date: 2026-06-29
Source: .primer/prd/PRD-004-nexus-replatform-checklist.md, .primer/brainstorming/2026-06-29-nexus-assess-migration.md

## Goal

Ship the replatform analysis subsystem: a new `src/nexus/replatform/`
package with a deterministic use-case classifier, a bi-directional
checklist diff, and a reporter, surfaced as two new subcommands under a
restructured `nexus assess` Typer group. v1 is LLM-free and bi-directional;
AI enrichment is deferred to v2 (2026.07 Agent Specialists). The shipped
gate/health behavior of `nexus assess` is preserved unchanged.

## Requirements Inventory

### Functional Requirements

* FR1: `src/nexus/replatform/models.py` -- `WorkflowRef`, `UseCase`,
  `UseCaseInventory`, `ChecklistItem`, `MigrationChecklist`, status/kind
  enums; all frozen+strict+extra=forbid.
  [Source: PRD-004#In Scope, brainstorm#Recommendation 2]
* FR2: Deterministic `classify(captures, scopes, plugin_inventory, catalog)
  -> UseCaseInventory` pure function, no I/O/LLM/MCP.
  [Source: PRD-004#In Scope, brainstorm#Recommendation 3]
* FR3: Pinned natural-key normalization
  `key = f"{scope}|{type}|{casefold(collapse_ws(name))}"` from
  `ScopeEntry.scope`; never sys_id.
  [Source: PRD-004#In Scope, brainstorm#Recommendation 4, ADR-025#Decision 2]
* FR4: `build_checklist(source, target, aliases) -> MigrationChecklist`
  with workflow-grain TODO/DONE/EXTRA and use-case rollup
  DONE/TODO/PARTIAL(built/total); `--scope-alias` remap.
  [Source: PRD-004#In Scope, brainstorm#Recommendation 5]
* FR5: Reporter reusing `ui/components/` for console + a markdown emitter
  for `--out`; prominent empty/thin-coverage Notice.
  [Source: PRD-004#In Scope, brainstorm#Recommendation 6]
* FR6: `assess` converted to a Typer group preserving bare gate/health
  behavior behind an `invoke_without_command` + `ctx.invoked_subcommand`
  guard. [Source: PRD-004#In Scope, brainstorm#Recommendation 8, ADR-025#Decision 4]
* FR7: `nexus assess inventory <profile>` and `nexus assess migration
  --from --to [--scope-alias ...]` wired via `ReplatformCollaborators`
  (ctx.obj). [Source: PRD-004#In Scope, brainstorm#Recommendation 8]

### Non-Functional Requirements

* NFR1: 100% line coverage on every new module. [Source: charter.md, governance.md]
* NFR2: pyright strict + mypy strict, 0 errors, no `# type: ignore`.
  [Source: ADR-007, ADR-012]
* NFR3: Pydantic frozen+strict+extra=forbid. [Source: ADR-021, patterns.md]
* NFR4: File-size caps -- src/ 800, tests/ 1400. [Source: ADR-023]
* NFR5: No mocks; fakes in `tests/fakes/`. [Source: charter.md, governance.md]

### Constraints

* C1: Layer order -- `replatform` imports from `capture`, `plugins`,
  `instances`, `config`; never from `cli` or `agents`. [Source: ADR-025, patterns.md]
* C2: Advisory only -- the layer never mutates instance state.
  [Source: charter.md#3, ADR-025#Decision 3]
* C3: No MCP / live query inside the analysis layer. [Source: ADR-025#Decision 5]
* C4: Python 3.14 syntax; ASCII only; UTC datetime. [Source: CLAUDE.md, ADR-006]

## Coverage Map

| Requirement | Story | Status |
|---|---|---|
| FR1 | 01-replatform-models | backlog |
| FR2 | 02-classifier | backlog |
| FR3 | 02-classifier | backlog |
| FR4 | 03-checklist-diff | backlog |
| FR5 | 04-reporter | backlog |
| FR6 | 05-assess-group-restructure | backlog |
| FR7 | 06-assess-subcommands | backlog |
| NFR1-5 | all stories | backlog |
| C1-4 | all stories | backlog |

## Story List

| # | Title | Dependencies | Status |
|---|---|---|---|
| 01 | replatform-models | none | backlog |
| 02 | classifier | 01 | backlog |
| 03 | checklist-diff | 01 | backlog |
| 04 | reporter | 01 | backlog |
| 05 | assess-group-restructure | none | backlog |
| 06 | assess-subcommands | 02, 03, 04, 05 | backlog |

## Progress

Stories: 6/6 done -- COMPLETE

## Out of Scope (this epic)

* **AI enrichment (`enrichment.py`)** -- specialist-driven naming +
  sub-clustering; v2, depends on the 2026.07 Agent Specialists work.
* **Capture-layer changes** -- depends on the existing `AI_AUTOMATION`
  group; no new table groups (the `DEVELOPER_PLATFORM` extension is a
  separate backlog item).
* **Auto-build on the target (`--apply`)** -- advisory only per ADR-025.
* **Fuzzy/semantic workflow matching** -- exact normalized-key +
  `--scope-alias` only.
* **Changes to gate/RuleEngine semantics** -- bare `assess` / `--for` /
  `--job` are preserved, not modified.

## References

* PRD: `.primer/prd/PRD-004-nexus-replatform-checklist.md`
* Brainstorming: `.primer/brainstorming/2026-06-29-nexus-assess-migration.md`
* ADR: `.primer/adr/ADR-025-replatform-cross-instance-analysis.md`
* ADR: `.primer/adr/ADR-003-assessment-3-gate-model.md`
* Existing capture: `src/nexus/capture/` (models.py, tables.py, archive.py)
* Existing diff pattern: `src/nexus/plugins/diff.py`, `src/nexus/plugins/drift.py`
* Existing CLI: `src/nexus/cli/commands_assess.py`, `commands_top.py`
* Existing UI: `src/nexus/ui/components/`
