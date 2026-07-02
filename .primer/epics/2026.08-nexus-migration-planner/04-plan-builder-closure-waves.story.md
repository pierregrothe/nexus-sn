# Story 04: plan builder -- closure + waves

Status: done
Spec-Clarity: high
Depends-On: 01, 02

## Recon decision (2026-07-02)

Closure must never silently override an explicit `exclude` disposition
(the "exclusion means never-migrate" design principle -- brainstorm#Key
Insight 3). This story therefore treats the three `SelectionItem`
dispositions asymmetrically during closure:

- `include`: in the plan.
- `undecided`: closure MAY auto-add a referenced item, marked
  `added_by_closure=True`, for the consultant to review later.
- `exclude`: never auto-added; if something included references it,
  closure raises a `STRANDED_DEPENDENCY` finding instead.

This is the biggest story in the epic -- generous table-based AC per
closure rule, plus GWT for every blocking path.

## Story

As a NEXUS developer building the migration planner's dependency-safety
guarantee,
I want a pure closure/wave builder that expands a curated Selection into
its structured dependency closure, dampens core-table references into
DATA_PREREQUISITE findings, orders items into topologically-sorted waves,
and blocks approval on unwaived/unacknowledged findings,
so that a plan can never silently strand a dependency.

## Acceptance Criteria

AC1 (reference-field closure, rule table):
| Rule | Input | Expected effect |
|---|---|---|
| Included item references an included item | edge A(include)->B(include) | edge recorded for wave ordering; no finding |
| Included item references an undecided item, target off stop-list | edge A(include)->B(undecided) | B added to plan, `added_by_closure=True`; no finding |
| Included item references an explicitly excluded item, target off stop-list | edge A(include)->B(exclude) | `STRANDED_DEPENDENCY` finding on A naming B; B is NOT added |
| Included item references any item whose target table is on the core-table stop-list | edge A(include)->core_table_row | `DATA_PREREQUISITE` finding naming the table; the row is never added to the plan |
| Included item has no outbound references | isolated A(include) | no edge, no finding; A placed in the earliest wave its own inbound edges allow |

AC2 (co-capture rules, rule table):
| Rule | Input | Expected effect |
|---|---|---|
| `sys_security_acl` selected | ACL A included | its `sys_security_acl_role` rows are always added, `added_by_closure=True`, never gated by disposition or stop-list |
| `sysauto_script` selected, references a script include | scheduled job A included, referenced script include B | B follows the standard reference-field closure rule (AC1 rows 2-3) |
| `sys_hub_flow` selected | Flow F included | its snapshot + subflow + action closure rows are always added, `added_by_closure=True` |

AC3 (sys_scope_privilege presence check):
**Given** an included artifact in scope S1 referencing an artifact in scope
S2 (S1 != S2)
**When** the OLD capture lacks a `sys_scope_privilege` record granting S1
access to S2
**Then** closure emits a `STRANDED_DEPENDENCY`-kind finding whose `detail`
names the missing scope-privilege grant.

AC4 (sys_db_object access-posture diff):
**Given** a selected table present in both OLD and NEW captures with
differing `accessible_from`/`caller_access` field values
**When** closure runs
**Then** it emits an `ACCESS_POSTURE_DRIFT`-kind finding naming the table
and both values. `ACCESS_POSTURE_DRIFT` is added to `FindingKind` in this
story (Story 02 declared the enum open with "at minimum").

AC5 (configurable stop-list):
**Given** a closure run with a custom stop-list (e.g. loaded from Story
00's `seed-stop-list.yaml`)
**When** a reference target's table is in the custom list
**Then** dampening applies exactly as AC1's stop-list row, using the custom
list instead of the hardcoded default.

AC6 (topological wave ordering):
**Given** a DAG of included + closure-added items and their reference
edges
**When** `build_waves(items, edges) -> tuple[Wave, ...]` runs
**Then** every item's wave index is strictly greater than every item it
depends on's wave index (a valid topological order), and items with no
ordering constraint between them share the earliest possible wave.

AC7 (cycle handling, GWT):
**Given** a reference cycle among included items (A->B->C->A)
**When** wave ordering runs
**Then** it does not raise and does not silently break the cycle -- it
emits a `CYCLE`-kind finding naming every item in the cycle, and those
items are placed together in a single wave rather than dropped from the
plan.

AC8 (approval blocking -- stranded without waiver, GWT):
**Given** a `MigrationPlan` with an unwaived `STRANDED_DEPENDENCY` finding
**When** `validate_approval(plan) -> tuple[str, ...]` runs
**Then** it returns at least one blocking reason.

AC9 (approval blocking -- waiver present, GWT):
**Given** the same plan with that finding's `waiver` populated
**When** `validate_approval(plan)` runs
**Then** that finding no longer contributes a blocking reason.

AC10 (approval blocking -- DATA_PREREQUISITE without acknowledgment, GWT):
**Given** a `MigrationPlan` with a `DATA_PREREQUISITE` finding lacking an
`acknowledgment`
**When** `validate_approval(plan)` runs
**Then** it returns a blocking reason; once an `Acknowledgment` is
attached, that finding no longer blocks.

## Must NOT

- Must NOT issue any live ServiceNow call -- closure and wave-building are
  pure functions over captured inputs (`CaptureResult` tuples) + offline
  schema-graph archives.
- Must NOT implement lane-binding/transport logic (APP_REPO/UPDATE_SET/DATA
  execution) -- `PlanItem.lane` is set to a provisional advisory default
  only; binding behavior is ADR-027 territory.
- Must NOT silently override an explicit `exclude` disposition -- closure
  never adds an explicitly excluded item; it raises a finding instead.

## Tasks / Subtasks

- [x] Create `src/nexus/migrate/closure.py` -- reference-field closure walk
      over `CaptureResult` + schema graph (AC1)
- [x] Implement co-capture rules (ACL->ACL-role, sysauto_script->script,
      sys_hub_flow->snapshot/subflow/action) (AC2)
- [x] Implement `sys_scope_privilege` presence check (AC3)
- [x] Implement `sys_db_object` accessible_from/caller_access diff; add
      `ACCESS_POSTURE_DRIFT` to `FindingKind` in `src/nexus/migrate/models.py`
      (AC4)
- [x] Implement configurable core-table stop-list + DATA_PREREQUISITE
      dampening, defaulting to Story 00's seed list (AC1, AC5)
- [x] Create `src/nexus/migrate/planner.py` -- `build_waves` topological
      sort + `CYCLE` finding emission (AC6, AC7)
- [x] Implement `validate_approval(plan) -> tuple[str, ...]` blocking-reason
      function (AC8-AC10)
- [x] Create `tests/fakes/migrate_closure.py` -- small fixture
      CaptureResult/schema-graph pairs covering each rule row
- [x] Create `tests/test_migrate_closure.py`, `tests/test_migrate_planner.py`
      (AC1-AC10)

## Existing Code

- `src/nexus/plugins/impact.py` -- `fetch_cross_scope_refs`/
  `fetch_scope_record_counts` shape (closure reuses the reference-edge
  concept, computed offline over captures rather than live).
- `src/nexus/schema/discoverer.py`, `src/nexus/schema/bridge.py` --
  reference/inheritance graph + `bridge_subgraph` used to resolve
  cross-table reference fields.
- `src/nexus/migrate/capture_bridge.py` (Story 01) -- supplies the full
  CaptureResults closure walks over.
- `src/nexus/migrate/models.py` (Story 02) -- `IntegrityFinding`,
  `FindingKind`, `PlanItem`, `Wave`, `Waiver`, `Acknowledgment`,
  `MigrationPlan`.

## Dev Notes

### Modules Affected

- `src/nexus/migrate/closure.py`, `src/nexus/migrate/planner.py` (new)
- `src/nexus/migrate/models.py` (extend `FindingKind` with
  `ACCESS_POSTURE_DRIFT`)
- `tests/fakes/migrate_closure.py`, `tests/test_migrate_closure.py`,
  `tests/test_migrate_planner.py` (new)

### Testing Approach

- Function-based pytest, `test_<func>_<scenario>` per closure rule row
  (e.g. `test_closure_stranded_dependency_on_explicit_exclude`,
  `test_closure_data_prerequisite_on_stop_list_table`,
  `test_build_waves_reports_cycle_as_finding`).
- No mocks; fixtures in `tests/fakes/migrate_closure.py` build small
  hand-crafted `CaptureResult` + schema-graph pairs per rule, not the full
  30K dataset (that measurement is Story 00's job).
- Positive, negative, and stop-list-dampening cases are each dedicated
  tests per PRD-005's closure acceptance-criteria bullet.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (Closure
  rules v1, Core-table dampening, Approval and audit model),
  `#Acceptance Criteria` (closure rule tests, waiver/acknowledgment
  blocking, wave-ordering bullets)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 3`
  (full dependency treatment + dampening), `#Decision 5` (lanes are
  advisory hints)
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Recommendation 3`
  (closure rules v1 + documented-gap register), `#Research Findings
  Appendix` (Silent-breakage dependency taxonomy)
