# Story 06: `plan --recheck` drift detection

Status: done
Spec-Clarity: high
Depends-On: 05

## Story

As a Solution Consultant about to execute a wave by hand days after a plan
was generated,
I want `nexus migrate plan --recheck` to re-inventory both instances and
report drift against the plan's snapshots,
so that I never execute against a stale, silently-changed instance state.

## Acceptance Criteria

AC1 (no-drift case, GWT):
**Given** a `MigrationPlan` whose source/target snapshot identities match a
fresh lightweight re-inventory of both instances (same artifact set)
**When** `nexus migrate plan --recheck --plan plan.yaml` runs
**Then** it reports "no drift detected", leaves the runbook marked valid,
and exits 0.

AC2 (drift-detected case, GWT):
**Given** a plan whose source instance has an artifact added or removed
since the snapshot
**When** `--recheck` runs
**Then** it reports the added/removed/changed artifacts (by natural key)
grouped by instance (source/target) and by change kind, marks the runbook
stale, and exits 2.

AC3 (exit-code table):
| Outcome | Exit code |
|---|---|
| No drift | 0 |
| Drift detected (added/removed/changed artifacts) | 2 |
| Instance/plan unreachable or unreadable (hard error) | 1 |

AC4 (changed-artifact detection):
**Given** an artifact present in both the original snapshot and the
recheck listing but with a different captured field fingerprint
**When** `--recheck` runs
**Then** it is reported under "changed", distinct from "added"/"removed".

AC5 (runbook stale marking):
**Given** a drift-detected recheck
**When** it completes
**Then** the plan's runbook is rewritten via the Story 05 `render_runbook`
header path with a STALE banner (not a second, ad hoc output convention
such as a companion `.stale` marker file).

## Must NOT

- Must NOT write to either ServiceNow instance -- `--recheck` performs
  read-only re-inventory only (reusing the replatform-style lightweight
  listing).
- Must NOT silently overwrite the original plan.yaml's approval block --
  drift detection produces a report and a stale runbook banner; it never
  clears `approved_by`/`approved_at` itself (a human re-approves after
  reviewing drift, per ADR-026#Decision 2's git-review model).

## Tasks / Subtasks

- [x] Create `src/nexus/migrate/recheck.py` -- `compute_drift(plan,
      source_listing, target_listing) -> DriftReport` (AC1-AC4)
- [x] Define a `DriftReport` frozen model in `src/nexus/migrate/models.py`
      (added/removed/changed per instance) (AC2-AC4)
- [x] Wire `--recheck` + `--plan` options onto the existing
      `@migrate_app.command("plan")` (Story 05), branching to the recheck
      path reusing the replatform-style lightweight live listing (AC1-AC3)
- [x] Implement the runbook STALE header rewrite via `render_runbook` (AC5)
- [x] Create `tests/test_migrate_recheck.py`, `tests/cli/test_migrate_plan_recheck_cmd.py`
      (AC1-AC5)

## Existing Code

- `src/nexus/cli/commands_assess_replatform.py` `_list_artifacts_live` --
  the lightweight (name/type/scope only) live-listing pattern this story
  reuses for the recheck's re-inventory pass.
- `src/nexus/migrate/runbook.py` (Story 05) -- shared render path for the
  STALE header rewrite.
- `src/nexus/migrate/models.py` (Story 02/04) -- `MigrationPlan` snapshot
  identities being compared against.

## Dev Notes

### Modules Affected

- `src/nexus/migrate/recheck.py` (new)
- `src/nexus/migrate/models.py` (add `DriftReport`)
- `src/nexus/cli/commands_migrate.py` (add `--recheck`/`--plan` to `plan`)
- `tests/test_migrate_recheck.py`, `tests/cli/test_migrate_plan_recheck_cmd.py`
  (new)

### Testing Approach

- Function-based `test_<func>_<scenario>` tests, e.g.
  `test_compute_drift_reports_added_artifact`,
  `test_compute_drift_no_drift_exit_zero`.
- No mocks; recheck tests inject two listing fixtures (before/after) via
  `tests/fakes/migrate.py`, never a live client.
- CLI test via `CliRunner` with an injectable listing seam mirroring Story
  06 of the 2026.07 epic's fake-inventory-builder pattern.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (`plan
  --recheck` bullet), `#Acceptance Criteria` (recheck drift bullet)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 4`
  (freshness enforced, not assumed)
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Key Insight 7`
  (plan-vs-reality drift is a first-class failure mode)
