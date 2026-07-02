# Story 07: `nexus migrate preflight`

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a Solution Consultant preparing to hand a plan to an executor,
I want `nexus migrate preflight` to probe both instances read-only for
execution preconditions,
so that CICD plugin absence, missing sn_cicd role, app-repo entitlement
gaps, and auth-mode surprises are known before anyone attempts execution.

Note: this story folds spike S1 (CICD availability probe) per the
brainstorm's resolved disposition #6 -- `preflight` ships in this
milestone, read-only, and is the natural home for S1's logic rather than a
separate spike-track story.

## Acceptance Criteria

AC1 (probe items, table):
| Item | Signal probed | Pass condition |
|---|---|---|
| CICD plugin | `com.glide.continuousdelivery` presence via the existing plugin inventory read | plugin present + active |
| sn_cicd role grantability | `sn_cicd.sys_ci_automation` role existence signal (a read against `sys_user_role`) | role record readable; a 403 is reported unknown, not fail |
| App-repo entitlement | `sys_app` publish-field readability (a scoped read against `sys_app` for publish-related fields) | fields readable -> pass; 403 -> fail; 404/absent table -> unknown |
| Auth mode | whether the connected profile's auth is OAuth or Basic, from the instance registry auth metadata | always reported, never blocks |

AC2 (pass/fail/unknown, GWT):
**Given** any probe item
**When** the underlying read returns 200
**Then** it is reported `pass`; **when** it returns 403
**Then** it is reported `fail`; **when** it returns 404 or another
non-403 error (table absent, network hiccup)
**Then** it is reported `unknown` -- `preflight` never raises on a 403.

AC3 (rendered like diagnose-roles):
**Given** a `preflight` run
**When** rendered
**Then** its console table shape mirrors `instance diagnose-roles` (item,
status cell, purpose/description, suggested remediation, detail), reusing
the same row-building pattern.

AC4 (both instances probed):
**Given** `nexus migrate preflight --from <old> --to <new>`
**When** run
**Then** every applicable item is probed against both instances and the
report is grouped per instance, stating explicitly which side each item
targets.

AC5 (never writes, GWT):
**Given** any `preflight` invocation
**When** it completes, regardless of outcome
**Then** it has issued zero POST/PUT/PATCH/DELETE calls to either
instance -- GET-only.

## Must NOT

- Must NOT write to either ServiceNow instance -- GET-only probes, no
  state changes, ever (advisory/read-only, charter hard limit 4).
- Must NOT raise an unhandled exception on any 403/404 from a probe target
  -- every probe item degrades to `fail`/`unknown` per AC2, mirroring
  `role_probe.probe_table_access`'s network-error-as-status-0 pattern.
- Must NOT duplicate `role_probe.py`'s table-probe primitive -- reuse
  `probe_table_access`/`probe_all` rather than reimplementing HTTP GET +
  error-body parsing from scratch.

## Tasks / Subtasks

- [ ] Create `src/nexus/migrate/preflight.py` --
      `MIGRATE_PREFLIGHT_PROBES` + `run_preflight(client_old, client_new)
      -> PreflightReport` (AC1, AC4)
- [ ] Reuse `src/nexus/instances/role_probe.py`'s `probe_table_access` for
      the sn_cicd-role and app-repo-entitlement table reads (AC1, AC5)
- [ ] Implement the CICD-plugin-presence check via the existing
      plugin-scan primitive (AC1)
- [ ] Implement the auth-mode report from the instance registry metadata
      (AC1)
- [ ] Define `PreflightReport`/`PreflightItemResult` frozen models in
      `src/nexus/migrate/models.py` (pass/fail/unknown enum) (AC1, AC2)
- [ ] Wire `@migrate_app.command("preflight")` rendering like `instance
      diagnose-roles` (AC3)
- [ ] Create `tests/test_migrate_preflight.py`, `tests/cli/test_migrate_preflight_cmd.py`
      (AC1-AC5)

## Existing Code

- `src/nexus/instances/role_probe.py` -- `TableProbe`,
  `probe_table_access`, `probe_all`, `DEFAULT_PROBE_TABLES` (the primitive
  and pattern this story reuses/extends).
- `src/nexus/cli/commands_instance.py` `instance_diagnose_roles` -- the
  rendering pattern (status cell ok/fail, row-building).
- `src/nexus/plugins/scanner.py` -- existing plugin-inventory read used
  for the CICD-plugin-presence check.
- `src/nexus/instances/registry.py` -- profile/auth-mode metadata.

## Dev Notes

### Modules Affected

- `src/nexus/migrate/preflight.py` (new)
- `src/nexus/migrate/models.py` (add `PreflightItemResult`/
  `PreflightReport`/status enum)
- `src/nexus/cli/commands_migrate.py` (add `preflight` command)
- `tests/test_migrate_preflight.py`, `tests/cli/test_migrate_preflight_cmd.py`
  (new)

### Testing Approach

- Function-based `test_<func>_<scenario>` tests, e.g.
  `test_run_preflight_reports_fail_on_403`,
  `test_run_preflight_reports_unknown_on_404`.
- No mocks; probe tests use a fake `httpx.AsyncBaseTransport` (the same
  transport-injection pattern `role_probe.py`'s own tests already use), not
  `unittest.mock`.
- CLI test via `CliRunner` with fake clients injected through the
  collaborators seam.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (`nexus
  migrate preflight` bullet), `#Acceptance Criteria` (preflight
  pass/fail/unknown bullet)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 6`
  (advisory-only milestone; preflight is read-only by construction)
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Recommendation 4`
  (preflight ships in milestone 1; home for spike S1), `#Research Findings
  Appendix` (App Repository / auth posture), `#Adversarial Review` Round 2
  disposition 6
