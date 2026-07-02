# Story 00: S0 closure-scale spike

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a NEXUS developer validating the migration planner's closure design
before building it,
I want a measurement harness that runs the existing cross-scope-ref,
record-count, and schema-graph primitives against the already-captured
30K-artifact live inventory JSONs,
so that closure wall-clock, finding counts (with/without a stop-list), and
lane-unit counts are known numbers before any full-estate curation is
offered to a customer.

## Acceptance Criteria

AC1 (harness inputs, no live calls):
**Given** `scripts/spike_s0_closure_scale.py`
**When** it runs
**Then** it loads `artifacts/replatform-proof/inventory-alectri-v2.json` and
`artifacts/replatform-proof/inventory-retail-v2.json` (regenerated via the
commands documented in `artifacts/replatform-proof/verification-summary.md`
"Regenerating the large artifacts") as its fixed input, and never opens a
`ServiceNowClient` / `httpx` connection.

AC2 (measurement table):
| Measurement | How obtained | Recorded where |
|---|---|---|
| Closure wall-clock at 30K artifacts | wrap the closure walk (reference-field closure over the loaded inventory + an offline schema-graph archive) with `time.perf_counter()` | epic.md Progress notes, row "S0 wall-clock" |
| Finding count without stop-list | run the closure walk with an empty stop-list; count resulting candidate findings | epic.md Progress notes |
| Finding count with candidate stop-list | run the same walk with the seed stop-list (sys_user, sys_user_group, sys_choice, cmdb_ci and kin) | epic.md Progress notes |
| Lane-unit count | count distinct scoped apps (custom scope keys) + update-set-sized config groupings + data-batch buckets (one per stop-list table hit) | epic.md Progress notes |

AC3 (seed stop-list output):
**Given** the harness run completes
**When** it writes output
**Then** it emits a seed stop-list YAML (flat list of table names) to
`.primer/epics/2026.08-nexus-migration-planner/seed-stop-list.yaml` for
Story 04's closure builder to load as its starting default.

AC4 (summary doc + epic Progress append):
**Given** the harness run completes
**When** it writes output
**Then** a summary is committed to
`.primer/epics/2026.08-nexus-migration-planner/s0-spike-results.md` with the
four AC2 measurements plus the exact regeneration commands used, and the
same numbers are appended to this epic's `epic.md` Progress section.

AC5 (never live, GWT):
**Given** any invocation of the harness, locally or in CI
**When** it runs
**Then** it constructs zero network clients -- it is pure over the
committed/regenerated JSON files.

## Must NOT

- Must NOT write to any ServiceNow instance -- no live calls of any kind;
  the harness is pure over already-captured JSON.
- Must NOT add new production modules under `src/nexus/` -- spike code
  lives under `scripts/` or `tests/spikes/` only.
- Must NOT commit the regenerated 6MB inventory JSONs themselves (per
  `verification-summary.md` they stay untracked/regenerable); only
  `seed-stop-list.yaml` and `s0-spike-results.md` are committed.

## Tasks / Subtasks

- [ ] Regenerate (or reuse locally) `inventory-alectri-v2.json` /
      `inventory-retail-v2.json` per the documented commands (AC1)
- [ ] Write `scripts/spike_s0_closure_scale.py`: load JSON, build a
      candidate closure walk over `plugins.impact`-shaped edges + a schema
      graph archive, time it with `time.perf_counter()` (AC1, AC2)
- [ ] Implement stop-list on/off measurement pass (AC2)
- [ ] Implement lane-unit counting heuristic (AC2)
- [ ] Emit `seed-stop-list.yaml` (AC3)
- [ ] Emit `s0-spike-results.md` + append numbers to `epic.md` Progress (AC4)
- [ ] Add a spike-level assertion that no network client is constructed
      (AC5)

## Existing Code

- `src/nexus/plugins/impact.py` -- `fetch_cross_scope_refs`,
  `fetch_scope_record_counts` (live versions; the spike reuses the edge
  shape offline, never the live call).
- `src/nexus/schema/discoverer.py`, `src/nexus/schema/bridge.py` --
  `SchemaDiscoverer` reference graph + `bridge_subgraph`.
- `artifacts/replatform-proof/verification-summary.md` -- exact
  regeneration commands ("Regenerating the large artifacts" section).

## Dev Notes

### Modules Affected

- `scripts/spike_s0_closure_scale.py` (new, spike-only, not under
  `src/nexus/`)
- `.primer/epics/2026.08-nexus-migration-planner/seed-stop-list.yaml` (new
  output artifact)
- `.primer/epics/2026.08-nexus-migration-planner/s0-spike-results.md` (new
  output artifact)
- `.primer/epics/2026.08-nexus-migration-planner/epic.md` (Progress section
  appended)

### Testing Approach

- `tests/spikes/test_spike_s0_closure_scale.py`, function-based
  `test_<func>_<scenario>` tests exercising the harness's pure functions
  (stop-list filtering, lane-unit counting) against a small fixture
  inventory in `tests/fakes/`, NOT the full 30K dataset.
- No mocks; a small fake JSON fixture stands in for the live-captured
  dataset in the unit-level tests.
- The full-scale timed run itself is a documented, human-run command (AC4)
  whose output feeds the epic's Progress notes -- it is not asserted inside
  the pytest suite, since CI should not depend on a 6MB untracked artifact.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (Spike
  track), `#Acceptance Criteria` (S0 bullet), `#Success Metrics`
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Context` (spike
  track), `#Decision 5`
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Recommendation 5`,
  `#Research Findings Appendix` (Repo primitives inventory)
