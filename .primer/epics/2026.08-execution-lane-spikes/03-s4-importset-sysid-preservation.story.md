# Story 03: S4 -- Import-set sys_id preservation

Status: backlog
Spec-Clarity: high
Depends-On: none

## Goal

Determine whether a scripted `onBefore` `setNewGuidValue` transform-map
assist actually preserves caller-supplied sys_ids on Import Set insert,
since declarative coalesce-on-sys_id does not (convergent community
reports cited in the research appendix).

## Method Sketch

1. Create a small staging table + transform map targeting a disposable
   custom table on the demo NEW instance.
2. Add an `onBefore` transform script calling `setNewGuidValue` with the
   caller-supplied sys_id.
3. Insert a handful of staging records with known sys_ids via `POST
   /api/now/import/{staging}`; run the transform; read back the resulting
   target-table records' sys_ids and compare to the staged values.
4. Separately test attachment behavior (does an attachment survive a
   transform-mapped insert) and journal-field behavior (do journal entries
   migrate, confirming or denying the known gap).

## Timebox

One working day. Limit table-type coverage to 2 representative tables (one
custom scoped-app table, one global-scope table) rather than an exhaustive
sweep.

## Acceptance Criteria

AC (questions answered, each recorded in the evidence file):
- Q1: Does `onBefore setNewGuidValue` preserve the caller-supplied sys_id
  on insert, and across which table types tested?
- Q2: What is the observed behavior with domain separation active (if the
  demo pair has it enabled) vs not?
- Q3: Do attachments survive a transform-mapped import-set insert
  unchanged?
- Q4: Do journal fields migrate via the same path, or must they be handled
  separately?

Evidence file: `.primer/epics/2026.08-execution-lane-spikes/s4-evidence.md`.

## Must NOT

- Must NOT run against any customer instance or customer data.
- Must NOT test with real or production-shaped data -- staged records are
  synthetic, disposable fixtures created for the spike.
- Must NOT leave the staging table, transform map, or inserted target
  records on the demo instance after the spike -- clean up before closing.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (Spike
  track, S4)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 5`
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Key Insight 5`
  (sys_id preservation), `#Research Findings Appendix` (Data lane
  section), `#Adversarial Review` Round 2 disposition 5 (PII/data-
  classification -- demo pair only, synthetic data)
