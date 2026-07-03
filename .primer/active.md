# NEXUS -- Active Work

Last updated: 2026-07-03
Session: PM-autonomous delivery of the 2026.08 migration-planner epic --
all 8 stories + 1 follow-up shipped (PRs #61-#69), plus epic close-out
(whole-epic 7-agent final review + live e2e validation, fixes in PRs
#70-#71). Everything merged to main; live-proven vs alectri/retail.

## Current Focus

On branch: main (all work merged)
Version: 2026.06.0 (tagged); migration planner shipped on main, unreleased

Active: `nexus migrate` family complete and live-proven -- select (seed a
Selection YAML from a checklist), plan (dependency closure + waves +
waiver/acknowledgment-gated approval + lane-shaped runbook + embedded drift
baselines), plan --recheck (drift detection, exit 0/2/1, STALE runbook
rewrite), preflight (GET-only execution-precondition probe, folds spike S1).
Advisory only per charter hard limit 4. Epic evidence and known-v1
characteristics: .primer/epics/2026.08-nexus-migration-planner/epic.md
Progress section.

Context: financial-services customer replatform (OLD -> NEW instance).
The planner turns the shipped replatform checklist into an auditable,
hand-executable migration plan. Execution lanes are a future milestone
gated on ADR-027 after the S2-S5 spike epic.

## Recent Changes

- b7b47c6 fix(cli): plan capture/schema clients carry token-refresh callback (#71)
- af19ab2 fix(migrate+cli): close live-e2e and final-review findings (#70)
- f6d11d0 feat(migrate+cli): nexus migrate preflight (story 07) (#69)
- e772e68 feat(migrate+cli): plan --recheck drift detection + STALE runbook (story 06) (#68)
- 591a4e4 feat(migrate+cli): nexus migrate plan + lane-shaped runbook (story 05) (#67)

## Open Blockers

- MCPProbe._check_server() still stubbed; enterprise MCP endpoints unknown.
- knowledge/mastery/ empty (decision pending: copy from JARVIS or rebuild).
- `nexus run`, `nexus rollback` still raise NotImplementedError.
- `nexus apply --live` capture-runner and ApplyEngine factory raise
  NotImplementedError until ServiceNowClient + CaptureEngine pairing wired.
- sys_update_xml direct-REST POST blocked by SN ACL even for admin via OAuth
  Bearer (superseded for config moves by the CICD Update Set API lane --
  spike S2 will validate; see ADR-027 track).
- Plugin deactivate/uninstall are SN-platform-blocked at the OAuth/REST
  boundary; surfaced as clean failures.
- Kroki public instance (kroki.io) intermittently hits disk-full errors;
  local graphviz renderer is on the roadmap as the replacement.
- sys_security_acl listing returns 400/404 on the demo pair (absent-table
  warning covers it); root cause on a customer instance TBD.

## Next Steps

1. Execution-lane spike epic (S2-S5, demo pair only) -- results gate
   ADR-027; epics/2026.08-execution-lane-spikes/.
2. Migration-planner v1.1 backlog (recorded in epic.md Progress): per-
   (scope,table) fetch tightening for full-estate selections; USE_CASE
   include propagation UX decision; deferred minors (_cell dedup, DriftReport
   grouping helper, closure record indexes, Literal instance field).
3. PRD-005 open questions need customer input: change-request linkage depth,
   promotion tiers (dev->test->prod) on the NEW side.
4. Git history still contains the customer name in pre-scrub commits --
   history rewrite + force push remains the user's call.

## Branch / remote state

On main, synced with origin (b7b47c6). Latest tag: 2026.06.0.
