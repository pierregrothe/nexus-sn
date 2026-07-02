---
id: PRD-005
title: NEXUS Migration Planner -- nexus migrate select / plan / preflight
status: draft
date: 2026-07-02
adrs: [ADR-026, ADR-025]
charter_link: charter.md#3-hard-product-limits
milestone: 2026.08-migration-planner
---

# PRD-005: NEXUS Migration Planner -- `nexus migrate select` + `plan` + `preflight`

## Problem

The replatform checklist (PRD-004, shipped + coverage-extended) tells a
customer WHAT differs between the OLD and NEW instance. It does not help them
decide what to migrate, prove the selection will not strand interdependencies,
order the work safely, or hand an executor (human today, tool later) an
auditable plan. ServiceNow has no native row-level selective-migration
primitive: update-set preview checks only its own batch, clone excludes are
whole-table, and six-plus classes of dependency breakage are entirely silent.
This PRD ships the planning half of selective migration: a curated selection,
a dependency-closure and integrity analysis, wave ordering, and a runbook --
all advisory, all read-only.

## Users

* Solution Consultants / architects running a selective replatform for a
  large regulated customer (choose what moves; deliberately leave the rest).
* Customer change-management stakeholders who must approve, audit, and track
  the migration plan.
* The future `migrate execute` lanes (second milestone), which consume the
  same plan artifact.

## In Scope (must-haves)

* **`src/nexus/migrate/` package** (new, separate from `replatform/` per
  ADR-026). Frozen+strict+extra=forbid models: `Selection`, `MigrationPlan`,
  `Wave`, `PlanItem` (with PROVISIONAL advisory `lane` hint), 
  `IntegrityFinding`, `Waiver`, `Acknowledgment`. Every plan carries
  `schema_version` and source-snapshot identities (instance, captured_at).
* **`nexus migrate select`** -- seed a selection YAML from a checklist:
  every use case / artifact with an include/exclude disposition and room for
  attributed annotations. The file lives in the engagement repo; git PR
  review is the collaboration and approval mechanism (branch protection with
  required reviewers is a stated engagement precondition).
* **`nexus migrate plan`** -- from the selection + full captures of both
  instances: dependency-closure expansion (additions explicitly marked
  `added-by-closure` for review), integrity findings, topological wave
  ordering, advisory lane routing, and a runbook (`--out runbook.md`).
* **Closure rules v1 (structured only)**: reference-field closure from
  captures + schema graph; co-capture rules (`sys_security_acl` ->
  `sys_security_acl_role`; `sysauto_script` -> referenced script/script
  include; `sys_hub_flow` -> snapshot/subflow/action closure);
  `sys_scope_privilege` presence check; `sys_db_object`
  accessible_from/caller_access diff OLD vs NEW.
* **Core-table dampening**: a configurable stop-list (sys_user,
  sys_user_group, sys_choice, cmdb_ci and kin) where closure emits a
  `DATA-PREREQUISITE` finding instead of expanding the selection.
* **Approval and audit model (adversarial-mandated resolutions)**:
  - Stranded-dependency findings BLOCK a plan unless carried by an
    attributed `Waiver` (who, why, date). The waiver approver MUST differ
    from the plan author; the tool records both identities and refuses a
    self-approved waiver.
  - `DATA-PREREQUISITE` findings require an attributed `Acknowledgment`
    entry before a plan is approvable. Advisory-only handling is rejected.
  - The plan file carries an approval block; the runbook front page lists
    every waiver and acknowledgment verbatim.
* **Runbook**: unit of work is the lane-shaped unit (an app to install, an
  update set to move, a data batch, a manual rebuild step) -- never one line
  per artifact. Header carries generated-at, snapshot identities, and a
  validity window with an instruction to run `plan --recheck` before
  executing any wave by hand.
* **`nexus migrate plan --recheck`** -- re-inventory both instances, report
  drift against the plan's snapshots, and refresh or invalidate the runbook.
* **`nexus migrate preflight`** -- read-only probe of both instances for
  execution preconditions (CICD plugin, sn_cicd role, app-repo entitlement
  signal, auth mode), rendered like `instance diagnose-roles`.
* **Prerequisite fixes** (in-milestone; closure walks reference values):
  ConfigFetcher scalar fidelity (currently drops bool/number/null), and the
  selection-to-full-capture translation (checklist rows are name-only).
* **Spike track** (timeboxed; results due before full-estate curation is
  invited; S0 is the first story): S0 closure scale + false-positive burden
  + lane-unit count on the captured 30K-artifact live dataset; S1 CICD
  availability; S2 Update Source bootstrap + retrieve/preview/commit round
  trip; S3 curated update-set packaging on OLD (sn_cdm probe first);
  S4 import-set sys_id preservation; S5 app-repo publish/install round trip.
  Spikes run on the demo pair only, never on customer instances.

## Out of Scope (anti-creep fence -- the load-bearing section)

* **Any mutation of either instance.** This milestone is plan + runbook +
  preflight, read-only. Execution lanes are a separate future milestone
  behind ADR-027 and their own PRD, with their own human gates (charter hard
  limit 4).
* **Removal/deactivation on the NEW instance.** No supported OAuth surface
  exists; exclusion means never-migrate, by design.
* **Binding lane architecture.** `PlanItem.lane` is an advisory,
  schema-versioned hint; transports, auth posture (Basic-auth exception),
  and packaging are ADR-027 territory after spikes S1-S5.
* **Script-body scanning** (dot-walks, hardcoded sys_ids), **sys_domain
  separation**, **legacy Workflow internals closure**, **notification/email
  template refs**, **REST/SOAP message + MID/credential refs**, and
  **business-rule execution order**: named entries in the runbook's
  documented-gap register, not v1 checks.
* **Data-lane design** including PII/data-classification handling --
  explicitly deferred to ADR-027; plan model reserves the DATA-PREREQUISITE
  finding as the hook.
* **Fuzzy/semantic matching** (PRD-004 fence stands) and **IDR**.
* **Tool-built plan-file merge/collaboration machinery** -- git supplies it.
* **Waiver risk-tiering** -- v1 treats all waivers uniformly (deliberate
  simplification); a `risk_class` field is the named v1.1 extension point.
* **Promotion-chain execution** (dev -> test -> prod on the NEW side). The
  plan model must not preclude a target-chain field, but v1 plans target a
  single NEW instance. NEEDS CLARIFICATION with customer change management.

## Acceptance Criteria

- [ ] `migrate/` models frozen+strict+extra=forbid; mypy + pyright strict 0
  errors; 100% line coverage; plan files round-trip (emit -> load -> emit)
  byte-stable.
- [ ] `select` seeds a complete selection from a real checklist; every
  checklist item appears exactly once with a disposition.
- [ ] Closure: each v1 rule has dedicated tests (positive, negative, and
  stop-list dampening); closure additions are marked `added-by-closure`.
- [ ] Stranded-dependency plans are rejected without a waiver; waivers with
  author == approver are rejected; DATA-PREREQUISITE without acknowledgment
  blocks approval. All three paths tested.
- [ ] Wave ordering is a valid topological order of the dependency edges;
  cycles are reported as findings, never silently broken.
- [ ] Runbook renders lane-shaped units with the validity header and the
  waiver/acknowledgment front page; documented-gap register present verbatim.
- [ ] `plan --recheck` detects an artifact added/removed on either instance
  since the snapshot and reports drift.
- [ ] `preflight` reports each precondition with pass/fail/unknown against
  fakes; never writes.
- [ ] S0 measured on the live dataset: closure wall-clock and finding counts
  recorded in the epic before full-estate curation is offered to anyone.

## Success Metrics

* A consultant can produce an approved, waiver-complete plan for a bounded
  pilot use-case set in under a day, and the runbook is executable by hand
  without consulting the tool authors.
* Zero silent stranded dependencies on pilot execution (every breakage
  observed post-move traces to a documented-gap register entry, not a v1
  rule miss).
* S0: closure over the 30K-artifact dataset completes in minutes and yields
  a reviewable finding count (hundreds, not tens of thousands) with the
  stop-list applied.
* Re-running `assess migration` after manual execution of a wave shows the
  planned items flipping DONE with no EXTRA surprises.

## Dependencies

* **ADR-026** -- planner architecture, plan-file format, closure/waiver
  semantics (this PRD).
* **ADR-025 / PRD-004** -- checklist as input (shipped).
* **Capture layer** -- full-fidelity ConfigFetcher (fixed in-milestone) +
  ScopeDiscoverer (shipped).
* **impact.py / schema graph** -- cross-scope refs, record counts, reference
  edges (shipped; S0 validates scale).
* **ADR-027 (future)** -- execution lanes, auth posture, packaging; consumes
  this PRD's plan artifact unchanged.

## Open Questions

* Approval/audit depth: is plan-file approval + attributed waivers +
  journaled provenance sufficient, or does customer change management
  require external change-request linkage? (Customer input; blocks PRD
  finalization, not drafting.)
* Promotion tiers on the NEW side: single target or dev->test->prod chain?
  (Plan model reserves the field; customer input.)
* Update-set packaging on OLD: sn_cdm vs companion scripted-REST app vs
  pre-existing update sets only (spike S3; recorded in ADR-027).

## References

* Brainstorming: `.primer/brainstorming/2026-07-02-selective-migration-planner.md`
  (includes the research findings appendix and both adversarial rounds)
* Feasibility research workflow journal: wf_2fe96ce6-28f (session-local)
* ADR-026: selective-migration planner architecture
* PRD-004 / ADR-025: replatform checklist (input artifact)
* Roadmap: `.primer/roadmap.md` -- Migration Planner milestone
