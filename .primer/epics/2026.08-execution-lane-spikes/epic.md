# Epic: Execution-Lane Spikes (S2-S5) -- demo pair only

Phase: 2026.08
Date: 2026-07-02
Source: .primer/prd/PRD-005-nexus-migration-planner.md

## Goal

Run four timeboxed research spikes against the DEMO instance pair only
(never a customer instance) to answer the concrete platform-viability
questions ADR-026 deferred: does the CICD Update Set API round-trip
record-level config, can a curated update set be packaged on OLD, do
import sets preserve sys_ids, and does app-repo publish/install actually
work with the auth/entitlement posture NEXUS can support. Each spike
produces a recorded evidence file, not production code. The recorded
results of S2-S5 gate ADR-027 (binding execution lanes) -- until ADR-027 is
written, `PlanItem.lane` in the sibling migration-planner epic stays a
provisional, schema-versioned advisory hint only.

## Story List

| # | Title | Dependencies | Status |
|---|---|---|---|
| 01 | s2-update-source-cicd-roundtrip | none | backlog |
| 02 | s3-updateset-packaging-probe | none | backlog |
| 03 | s4-importset-sysid-preservation | none | backlog |
| 04 | s5-apprepo-publish-install | none | backlog |

## Out of Scope

- **Any customer instance.** Every spike runs against the demo pair
  (alectri/retail or an equivalent disposable pair) only.
- **Any production module.** Spike code and artifacts are research
  evidence, not `src/nexus/` modules; ADR-027 (written after this epic)
  decides what, if anything, becomes production code.
- **Any mutation beyond disposable demo-instance artifacts explicitly
  created for the spike and cleaned up.** No spike leaves durable state on
  the demo instances after it completes.

## Progress
- Stories: 0/4 done, 0 in-progress, 4 backlog

## References

* PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (Spike
  track)
* ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 5`
* Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Recommendation 5`,
  `#Research Findings Appendix`
* Sibling epic (gated by this epic's results): `epics/2026.08-nexus-migration-planner/`
* Adversarial disposition on data/PII spike scope:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Adversarial Review`
  Round 2, disposition 5
