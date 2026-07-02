# Story 04: S5 -- App-repo publish/install round trip

Status: backlog
Spec-Clarity: high
Depends-On: none

## Goal

Determine whether a tiny scoped application can be published from OLD and
installed on NEW via `sn_cicd app_repo`, and what entitlement/auth/role
reality gates that path.

## Method Sketch

1. Create a trivial scoped app on the demo OLD instance (e.g. one table +
   one business rule, no meaningful data).
2. Attempt `POST /api/sn_cicd/app_repo/publish` from OLD.
3. Attempt `POST /api/sn_cicd/app_repo/install` on NEW targeting the
   published app.
4. Record: entitlement behavior (does the same-company entitlement
   requirement block a demo/dev pair?), auth mode actually accepted (OAuth
   attempted first, then a Basic Auth Exception Account fallback per the
   2026 platform-policy note), role sufficiency
   (`sn_cicd.sys_ci_automation` alone vs supplemental `sys_app` ACLs), and
   whether any table row data moves with the app (expected: config only).

## Timebox

One working day. If same-company entitlement blocks install outright on
the first attempt, record that as the headline finding and stop rather
than pursuing entitlement workarounds.

## Acceptance Criteria

AC (questions answered, each recorded in the evidence file):
- Q1: Does publish/install succeed end to end on the demo pair, and with
  what exact status codes at each step?
- Q2: What auth mode is actually accepted (OAuth attempted first; Basic
  Auth Exception Account fallback recorded per policy)?
- Q3: Is `sn_cicd.sys_ci_automation` alone sufficient, or are supplemental
  `sys_app` ACLs required?
- Q4: Does any table row data move with the app, or is it config-only as
  expected?

Evidence file: `.primer/epics/2026.08-execution-lane-spikes/s5-evidence.md`.

## Must NOT

- Must NOT run against any customer instance -- demo pair only.
- Must NOT publish/install any app carrying real or production-shaped data
  -- the scoped app is a trivial, disposable fixture built for the spike.
- Must NOT leave the published/installed app on either demo instance after
  the spike -- uninstall/clean up before closing the story.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (Spike
  track, S5)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 5`
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Key Insight 6`
  (auth posture), `#Research Findings Appendix` (App Repository /
  sn_cicd app_repo section)
