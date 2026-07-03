# Epic: NEXUS Migration Planner -- `nexus migrate select` + `plan` + `preflight`

Phase: 2026.08
Date: 2026-07-02
Source: .primer/prd/PRD-005-nexus-migration-planner.md

## Goal

Take a shipped replatform checklist (PRD-004) the rest of the way: from "what
differs between OLD and NEW" to an approved, dependency-safe, auditable
migration plan a consultant can hand-execute. Ship `src/nexus/migrate/` --
frozen plan-file models, a curated `select`, a dependency-closure `plan` with
waiver/acknowledgment-gated approval and topological wave ordering, a
lane-shaped runbook, drift detection via `plan --recheck`, and a read-only
`preflight` probe. Advisory only, no mutation of either instance (charter
hard limit 4); binding execution lanes are a separate future milestone gated
on ADR-027.

## Requirements Inventory

### Functional Requirements

- FR1: `src/nexus/migrate/` package (new, separate from `replatform/`) --
  frozen+strict+extra=forbid models `Selection`, `MigrationPlan`, `Wave`,
  `PlanItem` (advisory `lane` hint), `IntegrityFinding`, `Waiver`,
  `Acknowledgment`; every plan carries `schema_version` and source-snapshot
  identities. [Source: PRD-005#In Scope; ADR-026#Decision 1-2]
- FR2: `nexus migrate select` seeds a `Selection` YAML from a checklist --
  every checklist item appears exactly once with an include/exclude
  disposition and room for attributed annotations.
  [Source: PRD-005#In Scope]
- FR3: `nexus migrate plan` orchestrates dependency-closure expansion
  (additions marked `added-by-closure`), integrity findings, topological
  wave ordering, advisory lane routing, and runbook emission (`--out
  runbook.md`). [Source: PRD-005#In Scope; ADR-026#Decision 3]
- FR4: Closure rules v1 (structured only) -- reference-field closure from
  captures + schema graph; co-capture rules (`sys_security_acl` ->
  `sys_security_acl_role`; `sysauto_script` -> referenced script/script
  include; `sys_hub_flow` -> snapshot/subflow/action closure);
  `sys_scope_privilege` presence check; `sys_db_object`
  accessible_from/caller_access diff OLD vs NEW.
  [Source: PRD-005#In Scope; brainstorm#Recommendation 3]
- FR5: Core-table dampening -- a configurable stop-list (sys_user,
  sys_user_group, sys_choice, cmdb_ci and kin) where closure emits a
  `DATA_PREREQUISITE` finding instead of expanding the selection.
  [Source: PRD-005#In Scope; brainstorm#Recommendation 3]
- FR6: Approval and audit model -- stranded-dependency findings BLOCK a plan
  unless carried by an attributed `Waiver` whose approver differs from the
  plan author; `DATA_PREREQUISITE` findings require an attributed
  `Acknowledgment`; the plan carries an approval block; the runbook front
  page lists every waiver/acknowledgment verbatim.
  [Source: PRD-005#In Scope; ADR-026#Decision 3; brainstorm#Adversarial Review Round 2]
- FR7: Runbook renders lane-shaped units (never one line per artifact); the
  header carries generated-at, snapshot identities, and a validity window
  instructing `plan --recheck` before hand-executing any wave.
  [Source: PRD-005#In Scope; ADR-026#Decision 4]
- FR8: `nexus migrate plan --recheck` re-inventories both instances, reports
  drift against the plan's snapshots, and refreshes or invalidates the
  runbook. [Source: PRD-005#In Scope; ADR-026#Decision 4]
- FR9: `nexus migrate preflight` -- read-only probe of both instances for
  execution preconditions (CICD plugin, sn_cicd role, app-repo entitlement
  signal, auth mode), rendered like `instance diagnose-roles`.
  [Source: PRD-005#In Scope; brainstorm#Recommendation 4]
- FR10: Prerequisite capture fixes -- `ConfigFetcher` scalar fidelity
  (bool/int/float/None currently dropped) and the selection-to-full-capture
  translation (checklist rows are name-only; closure needs full captures).
  [Source: PRD-005#In Scope; ADR-026#Decision 7]
- FR11: S0 closure-scale spike -- closure wall-clock, finding counts
  (with/without stop-list), and lane-unit count measured on the
  already-captured 30K-artifact live dataset, recorded before full-estate
  curation is offered to anyone. [Source: PRD-005#In Scope; PRD-005#Acceptance Criteria; PRD-005#Success Metrics]

### Non-Functional Requirements

- NFR1: 100% line coverage on every new module. [Source: PRD-005#Acceptance Criteria; charter.md]
- NFR2: mypy strict + pyright strict, 0 errors, no `# type: ignore`.
  [Source: PRD-005#Acceptance Criteria; CLAUDE.md]
- NFR3: Pydantic frozen+strict+extra=forbid on every `migrate/` model.
  [Source: PRD-005#Acceptance Criteria; patterns.md#pydantic-conventions]
- NFR4: Plan files round-trip (emit -> load -> emit) byte-stable.
  [Source: PRD-005#Acceptance Criteria]
- NFR5: No mocks; fakes in `tests/fakes/`. [Source: CLAUDE.md; patterns.md#testing]

### Constraints

- C1: Advisory-only milestone -- the planner never mutates either instance
  (charter hard limit 4). [Source: PRD-005#Out of Scope; ADR-026#Decision 6]
- C2: Layer order -- `migrate/` consumes `capture`, `plugins`, `instances`,
  `config`, and `replatform`'s `MigrationChecklist` output; it must not
  import `cli/` or `agents/`; `replatform/` stays ignorant of `migrate/`.
  [Source: ADR-026#Decision 1]

## Coverage Map

| Requirement | Story | Status |
|---|---|---|
| FR1 | 02-migrate-models-plan-roundtrip | done |
| FR2 | 03-migrate-select-cli | done |
| FR3 | 04-plan-builder-closure-waves, 05-runbook-plan-cli | done |
| FR4 | 04-plan-builder-closure-waves | done |
| FR5 | 04-plan-builder-closure-waves | done |
| FR6 | 04-plan-builder-closure-waves | done |
| FR7 | 05-runbook-plan-cli | done |
| FR8 | 06-plan-recheck-drift | done |
| FR9 | 07-migrate-preflight | done |
| FR10 | 01-full-fidelity-selective-capture | done |
| FR11 | 00-s0-closure-scale-spike | done |
| NFR1-5 | all stories | backlog |
| C1-2 | all stories | backlog |

## Story List

| # | Title | Dependencies | Status |
|---|---|---|---|
| 00 | s0-closure-scale-spike | none | done |
| 01 | full-fidelity-selective-capture | none | done |
| 02 | migrate-models-plan-roundtrip | none | done |
| 03 | migrate-select-cli | 02 | done |
| 04 | plan-builder-closure-waves | 01, 02 | done |
| 05 | runbook-plan-cli | 04 | done |
| 06 | plan-recheck-drift | 05 | done |
| 07 | migrate-preflight | none | done |

## Parallel Spike Track

Execution-lane viability (S2-S5) is researched in the sibling epic
`epics/2026.08-execution-lane-spikes/`, run in parallel with this epic's
build. Its recorded results gate ADR-027 (binding execution lanes) --
`PlanItem.lane` in this epic stays a provisional, schema-versioned advisory
hint until that ADR is written. Spikes run on the demo instance pair only,
never against a customer instance. S0 (closure scale) is Story 00 of *this*
epic, not the spike epic, because it validates this epic's own design before
any full-estate curation is offered to anyone.

## Out of Scope

- **Any mutation of either instance.** This milestone is plan + runbook +
  preflight, read-only. Execution lanes are a separate future milestone
  behind ADR-027 with their own human gates (charter hard limit 4).
- **Removal/deactivation on the NEW instance.** No supported OAuth surface
  exists; exclusion means never-migrate, by design.
- **Binding lane architecture.** `PlanItem.lane` is an advisory,
  schema-versioned hint; transports, auth posture (Basic-auth exception),
  and packaging are ADR-027 territory after spikes S1-S5.
- **Script-body scanning** (dot-walks, hardcoded sys_ids), **sys_domain
  separation**, **legacy Workflow internals closure**, **notification/email
  template refs**, **REST/SOAP message + MID/credential refs**, and
  **business-rule execution order** -- named entries in the runbook's
  documented-gap register, not v1 checks.
- **Data-lane design**, including PII/data-classification handling --
  explicitly deferred to ADR-027; the plan model reserves the
  DATA_PREREQUISITE finding as the hook.
- **Fuzzy/semantic matching** (PRD-004 fence stands) and **IDR**.
- **Tool-built plan-file merge/collaboration machinery** -- git supplies it.
- **Waiver risk-tiering** -- v1 treats all waivers uniformly (deliberate
  simplification); a `risk_class` field is the named v1.1 extension point.
- **Promotion-chain execution** (dev -> test -> prod on the NEW side). The
  plan model must not preclude a target-chain field, but v1 plans target a
  single NEW instance.

## Progress
- Stories: 8/8 done -- COMPLETE
- S0 wall-clock: 10.75ms (alectri, 30,463 artifacts, seed-stop-list walk; JSON load for both
  inventories + the schema archive is a separate 0.200s)
- S0 findings (no stop-list): raw 40,306 / deduped 351
- S0 findings (seed stop-list): raw 40,306 (expansion 40,306 / data-prerequisite 0) / deduped 351
  (expansion 351 / data-prerequisite 0) -- see s0-spike-results.md "Important caveat": none of the
  8 schema-declared reference edges for the 9 artifact tables target a stop-list table, so
  dampening measured zero here
- S0 lane-units: 95 = 82 scoped apps + 13 global use cases + 0 data batches
- Full details, regeneration commands, and the schema-graph edge list: see
  `s0-spike-results.md`
- Epic close-out (2026-07-02/03): whole-epic 7-agent final review (all findings
  adversarially verified) + live end-to-end validation vs alectri/retail found
  and fixed 3 Criticals + 2 Importants the per-story gates could not see (PRs
  #70-#71: rollup-key crash at 3 sites, recheck runbook-path divergence, missing
  preflight exports, silent natural-key-collision record drop, plan-wiring token
  refresh). Final live proof (bounded pilot selection, 6 items / 2 scopes):
  checklist JSON 9.9MB -> select seeded 27,959 items -> plan exit 0 (1 wave,
  0 findings; runbook 1.4KB + plan YAML 5.8MB with instance-wide baselines) ->
  recheck exit 0 "no drift detected" -> preflight all-PASS both instances.
  Suite at close: 2159 tests green, nexus.migrate 100% coverage.
- Known v1 characteristics recorded for v1.1: full-estate selections trigger
  disposition-blind capture of every named scope x table (a 27,959-item
  selection exceeds 10 min live) -- bounded pilot selections are the v1
  workflow; per-(scope,table) fetch tightening is the v1.1 fix. USE_CASE-level
  include is a documented no-op (propagation to member workflows is an open
  UX question). Deferred minors: _cell dict-unwrap triplication, DriftReport
  grouping duplication, closure linear scans, PreflightItemResult.instance
  as plain str.

## References

* PRD: `.primer/prd/PRD-005-nexus-migration-planner.md`
* ADR: `.primer/adr/ADR-026-selective-migration-planner.md`
* Brainstorming: `.primer/brainstorming/2026-07-02-selective-migration-planner.md`
* Sibling epic: `epics/2026.08-execution-lane-spikes/`
* Prior epic (input artifact): `epics/2026.07-nexus-replatform-checklist/`
* Existing capture: `src/nexus/capture/` (fetcher.py, models.py, archive.py)
* Existing replatform: `src/nexus/replatform/` (models.py, diff.py, reporter.py)
* Existing dependency primitives: `src/nexus/plugins/impact.py`,
  `src/nexus/schema/discoverer.py`, `src/nexus/schema/bridge.py`
* Existing probe pattern: `src/nexus/instances/role_probe.py`,
  `src/nexus/cli/commands_instance.py` (`diagnose-roles`)
