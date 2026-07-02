# Story 02: S3 -- Curated update-set packaging probe on OLD

Status: backlog
Spec-Clarity: high
Depends-On: none

## Goal

Determine whether a curated (hand-picked subset of records) update set can
be assembled programmatically on OLD, first via the `sn_cdm` deployables
endpoints, and -- only if that proves unusable -- via a design-only
(no-deployment) sketch of a companion scripted-REST packager.

## Method Sketch

1. Probe the `sn_cdm` export/upload/deployables endpoints catalogued in
   `docs/sn-internal-api-catalog.md` against the demo pair's OLD instance;
   record auth requirements, ACL behavior (200 vs 403 vs 404), and whether
   the endpoints assemble a curated subset or only a whole-app deployable.
2. If `sn_cdm` is unusable for curated packaging (undocumented, ACL-
   blocked, or wrong granularity), sketch -- design only, no deployment -- a
   companion scripted-REST packager: what Scripted REST API + Script
   Include shape would let NEXUS request "package these N sys_ids into
   update set X" and receive a retrievable update set.

## Timebox

One working day. If the first probed `sn_cdm` endpoint 404s outright,
spend no more than 2 hours confirming plugin absence before moving to the
design-sketch fallback.

## Acceptance Criteria

AC (questions answered, each recorded in the evidence file):
- Q1: Do the `sn_cdm` deployables export/upload endpoints exist and
  respond on the demo instance, and with what auth/ACL behavior?
- Q2: Do they operate at the granularity a curated selection needs
  (arbitrary record subset), or only at app/deployable granularity?
- Q3: If `sn_cdm` is unusable, what does the scripted-REST packager design
  sketch look like (endpoint shape, required Script Include, install
  footprint on OLD)?

Evidence file: `.primer/epics/2026.08-execution-lane-spikes/s3-evidence.md`.

## Must NOT

- Must NOT run against any customer instance -- demo pair only.
- Must NOT deploy the scripted-REST packager fallback -- design sketch
  only; no code committed under `src/nexus/` and no companion app
  installed on any instance.
- Must NOT leave any test deployable/export artifact on the demo instances
  after the spike.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (Spike
  track, S3)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 5`
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Research Findings Appendix`
  (Repo primitives inventory -- "Mined catalog lead: sn_cdm"), `#Open
  Questions` item 3
- Catalog: `docs/sn-internal-api-catalog.md`
