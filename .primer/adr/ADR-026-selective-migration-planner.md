# ADR-026: Selective-migration planner -- plan artifact, closure semantics, advisory lanes

**Status:** proposed
**Date:** 2026-07-02
**Enforcement:** agent
**prd:** PRD-005

## Context

The replatform checklist (ADR-025) answers "what differs" between an OLD and
a NEW instance but is deliberately advisory with no path from checklist to
action. The customer scenario -- selectively migrating chosen configuration
and its supporting data onto a clean instance without breaking
interdependencies -- needs a planning layer: curate a selection, prove it is
dependency-closed or explicitly waived, order it into waves, and emit an
auditable runbook. A 9-agent research pass (2026-07-02) established that
ServiceNow offers three partial execution lanes (sn_cicd app_repo for whole
scoped apps; the CICD Update Set API's retrieve/preview/commitMultiple for
record-level config, which supersedes the ACL-blocked raw sys_update_xml
push; Import Set/Table/Attachment/IRE APIs for data) but no native row-level
selective-migration or dependency-completeness primitive. Two adversarial
review rounds reshaped the design; the second returned "proceed" conditional
on the approval/audit resolutions now embedded in PRD-005. See
`.primer/brainstorming/2026-07-02-selective-migration-planner.md`.

## Decision

1. **Separate package.** Planning lives in a NEW `src/nexus/migrate/`
   package. It consumes `MigrationChecklist` (replatform), full
   `CaptureResult`s (capture), and dependency signals (plugins.impact +
   schema graph); it must not import cli/ or agents/, and replatform/ stays
   ignorant of it (layer order preserved).
2. **The plan file is the artifact of record.** A schema-versioned YAML
   (Selection -> MigrationPlan) that lives in the engagement repo; git PR
   review is the collaboration/approval mechanism. The plan embeds source
   snapshot identities and timestamps, an approval block, attributed
   Waivers, and attributed Acknowledgments. No tool-side merge machinery.
3. **Full dependency treatment with dampening.** `plan` expands the
   selection to its structured dependency closure (additions marked
   `added-by-closure`), topologically orders execution into waves, and
   BLOCKS plans that strand a dependency on the excluded side -- unless the
   finding carries a Waiver whose approver differs from the plan author.
   Core-table stop-list entries dampen closure into DATA-PREREQUISITE
   findings, which require an Acknowledgment; neither finding class is ever
   advisory-only.
4. **Freshness is enforced, not assumed.** Plans record what they were
   computed from; `plan --recheck` re-inventories and reports drift; the
   runbook header carries a validity window; any future execute command
   refuses a plan whose recheck is stale beyond the configured budget.
5. **Lanes are advisory hints in this milestone.** `PlanItem.lane`
   (APP_REPO | UPDATE_SET | DATA | MANUAL) is a provisional,
   schema-versioned routing hint for the runbook. The binding lane/transport
   architecture -- CICD update-set orchestration, app-repo entitlement and
   Basic-auth posture, update-set packaging on OLD, data-lane sys_id
   strategy and PII handling -- is deferred to ADR-027, written only after
   spikes S0-S5 report. A spike outcome may relabel lanes without
   invalidating plan files (schema_version tolerance).
6. **Advisory-only milestone; execution is a separate gated family.** The
   planner never mutates either instance (charter hard limit 4; ADR-025
   posture). Execution arrives later as `nexus migrate execute` with
   per-wave human approval modeled on PluginExecutor's confirm/--yes/
   type-to-confirm gates, stop-and-re-diff forward-fix failure posture, and
   no reliance on lane-native rollback.
7. **Closure computes from full captures.** The name-only checklist listing
   is insufficient; the planner requires the selection-to-full-capture
   translation and the ConfigFetcher scalar-fidelity fix (bool/number/null
   currently dropped) as in-milestone prerequisites.

## Consequences

- A consultant gets a dependency-safe, auditable, hand-executable runbook
  months before push-button execution exists; the same plan artifact feeds
  the future executor unchanged.
- The v1 closure is explicitly partial: script-body references, sys_domain,
  legacy Workflow internals, notifications, REST/MID/credential refs, and
  BR execution order live in a documented-gap register printed in every
  runbook, so the plan never implies completeness it does not have.
- Blocking-with-waivers trades some consultant friction for an audit trail a
  regulated customer can defend; the author/approver segregation is enforced
  by the tool, and branch protection on the engagement repo is a stated
  precondition rather than an assumption.
- Deferring binding lanes to ADR-027 keeps spike-refutable assumptions out
  of the plan schema; the cost is that runbook lane hints may change after
  spikes, bounded by running S0-S5 in parallel with the planner build and
  before full-estate curation.
- exclusion == never-migrate is a design principle (no supported OAuth
  removal surface exists on the platform); anything already on NEW that the
  customer does not want stays visible as EXTRA in the checklist rather
  than being deprovisioned by this tool.
