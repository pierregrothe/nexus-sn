# Story 01: S2 -- Update Source bootstrap + CICD Update Set round trip

Status: backlog
Spec-Clarity: high
Depends-On: none

## Goal

Determine whether NEXUS can bootstrap a CICD `sys_update_set_source`
pointing at the demo OLD instance via the Table API, and complete one
`retrieve -> preview -> commit` round trip of a small update set through
the CICD Update Set API -- the lane Key Insight 1 identifies as
ServiceNow's supported replacement for the ACL-blocked raw
`sys_update_xml` push.

## Method Sketch

1. On the demo OLD instance, create one small update set containing a
   trivial, disposable change (e.g. a single system property).
2. Via the Table API, attempt to create a `sys_update_set_source` record
   pointing at OLD (per the research appendix: Table-API-possible per a
   ServiceNow-employee community reply, but deliberately undocumented).
3. From the demo NEW instance, call `POST /api/sn_cicd/update_set/{retrieve,
   preview/{id},commit/{id}}` targeting the OLD source; poll
   `links.progress` until a terminal state.
4. Record every HTTP status code observed at each step, the
   preview-problem response body shape (if any preview problem arises),
   and the progress-polling response shape (fields present, terminal state
   values).

## Timebox

One working day. If `sys_update_set_source` creation via Table API is
rejected (403/404) on the first attempt, retry once with a corrected
payload shape, record the outcome, and stop -- do not pursue undocumented
workarounds beyond that.

## Acceptance Criteria

AC (questions answered, each recorded in the evidence file):
- Q1: Can `sys_update_set_source` be created via Table API pointing OLD ->
  the demo pair, and with what payload/response shape?
- Q2: Does the retrieve -> preview -> commit round trip succeed for one
  small update set, and what are the exact status codes at each step?
- Q3: What is the preview-problem response schema when a preview reports a
  problem (or "no problem observed" if none arose)?
- Q4: What is the progress-polling response shape (`links.progress`
  payload fields + terminal state values)?

Evidence file: `.primer/epics/2026.08-execution-lane-spikes/s2-evidence.md`
committed with the four answers above plus raw request/response
transcripts (credentials redacted).

## Must NOT

- Must NOT run against any customer instance -- demo pair only.
- Must NOT leave the created update set, update source, or any committed
  record on either demo instance after the spike -- clean up before
  closing the story.
- Must NOT add production code under `src/nexus/` -- this is a research
  spike; ADR-027 decides what, if anything, becomes production code.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (Spike
  track, S2)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 5`
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Recommendation 5`,
  `#Research Findings Appendix` (CICD Update Set API section), `#Key
  Insight 1`
