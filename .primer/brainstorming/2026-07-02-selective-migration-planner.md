# Brainstorming: Selective-Migration Planning and Execution (migrate select/plan/execute)

Date: 2026-07-02
Mode: assumptions
Techniques: assumptions-mode (seeded by a 9-agent research pass: 2 repo recon,
4 platform research, 3 adversarial refuters). Revised once after adversarial
review (revision log at bottom).

## Context Brief (condensed from primer-researcher + research pass)

Replatform v1 + coverage extension shipped and live-proven (30,463 artifacts,
95 named use cases across two table groups + global scope; multiset natural-key
diff; advisory-only per ADR-025 and charter hard limit 4). Existing execution
primitives: PluginExecutor (live-proven app install/activate/upgrade with
human gates), UpdateSetWriter (wired but ACL-blocked at sys_update_xml),
ApplyEngine (provenance-stamped skeleton, unwired). Dependency primitives:
impact.fetch_cross_scope_refs (scope-generic, live volume-ranked),
reverse_dependencies BFS, SchemaDiscoverer reference graph + bridge_subgraph,
SN's own /appmanager/dependencies resolver. src/nexus/execution/ is empty
stubs. Customer-instance preconditions (CICD plugin, app-repo entitlement,
auth posture) are engagement unknowns the repo cannot answer.

## Session Decisions (confirmed by user)

1. Selection UX: saved YAML plan file seeded from the checklist, curated in an
   editor, committed to the engagement repo; all later commands read it.
   Lifecycle model: single-owner file under git -- concurrent edits and
   approvals ride the engagement repo's normal PR review, not tool-invented
   merge machinery.
2. Dependency semantics: full treatment -- auto-expand selection to its
   dependency closure (additions marked for review), topological wave
   ordering, and blocking of plans that strand a dependency on the excluded
   side. Revised post-adversarial: the block is waivable -- each stranded
   dependency can carry an explicit, attributed waiver entry in the plan file
   (who, why, date); waivers are surfaced on the runbook's first page.
3. First milestone: plan + runbook (advisory, no new write paths). Revised
   post-adversarial: milestone 1 now explicitly includes the two capture
   prerequisites (see Rec 6) because closure computation walks reference-field
   VALUES, which the current name-only checklist listing does not carry.
   Execution lanes remain a second milestone gated on spikes.
4. Failure posture (for the later execute milestone): stop the wave, journal
   what was applied, forward-fix -- re-running assess migration is the source
   of truth; no reliance on lane-native rollback.

## Key Insights

1. The blocked path was the wrong path anyway. The CICD Update Set API
   (retrieve -> preview -> commit/commitMultiple, async with progress polling)
   is ServiceNow's supported replacement for raw sys_update_xml injection --
   it drives the same server-side workers as the UI, so the ACL does not
   apply. commitMultiple commits in caller-supplied order: the exact wave
   primitive a dependency-ordered migration needs.
2. Selectivity granularity is lane-dependent, so a selection is not one list.
   Whole scoped apps move via the app-repo lane (all-or-nothing per app);
   record-level config moves via update sets; row-level data moves via import
   sets. The RUNBOOK's unit of work is therefore the lane-shaped unit (an app
   to install, an update set to retrieve/commit, a data batch to import) --
   NOT 30K individual artifacts. Hand-execution feasibility is bounded by the
   count of those units (tens to low hundreds), not the artifact count.
3. Exclusion means never-migrate, not remove-later. No supported OAuth surface
   deactivates or uninstalls anything on the NEW instance. Design principle,
   stated up front.
4. The moat is the silent-breakage closure. ServiceNow has no row-level
   dependency-completeness check anywhere. The v1 structured taxonomy covers
   the highest-frequency classes; a documented-gap register covers the rest
   (see Rec 3) so the runbook never implies completeness it does not have.
5. sys_id preservation is the data-lane linchpin and is NOT natively
   guaranteed (coalesce mints fresh sys_ids on insert). Scripted-transform
   assist or a translation map -- spike S4 decides; data lane stays out of
   milestone 1.
6. Auth posture is product surface, not plumbing. sn_cicd is Basic Auth in
   practice; 2026 platform policy requires an explicit Basic Auth Exception
   Account. `migrate preflight` turns this into an early checklist item.
7. (Added post-adversarial) Plan-vs-reality drift is a first-class failure
   mode: instances keep changing between selection, planning, and (later)
   execution. Every plan records the source inventory snapshot identity and
   timestamps; `plan --recheck` re-inventories and reports drift; the future
   execute command refuses a plan whose recheck is stale beyond a
   configurable budget.

## Recommendations

1. Milestone "Migration Planner": new module src/nexus/migrate/ with frozen
   models Selection, MigrationPlan, Wave, LaneRoute (PROVISIONAL, see Rec 2),
   IntegrityFinding, Waiver; CLI group `nexus migrate` with `select`, `plan`,
   and `plan --recheck`. Advisory-only; charter-clean. Rationale: immediately
   converts the checklist into a dependency-safe, auditable execution plan the
   customer can act on while execution lanes mature. Scope guard: runbook
   units are lane-shaped work items, not per-artifact steps; a pilot on one
   bounded use-case subset precedes any full-estate plan.
2. Governance first: PRD-005 (migration planner; scope MUST include the
   approval/audit model: plan approval block, attributed waivers, runbook
   provenance, journal format) + ADR-026 (plan-file format with explicit
   schema_version, closure semantics, waiver semantics, freshness/recheck
   semantics). Lane routing in ADR-026 is limited to an ADVISORY,
   version-tolerant hint enum; the binding lane/transport architecture is
   ADR-027, written only after spikes S1-S5 report. Rationale: do not let a
   settled-looking schema encode lane assumptions the spikes exist to test.
3. Closure rules v1 (structured only), with an explicit completeness
   register. v1 checks: reference-field closure from full captures + schema
   graph; co-capture rules (sys_security_acl -> sys_security_acl_role;
   sysauto_script -> referenced script/script include; sys_hub_flow ->
   snapshot/subflow/action closure); sys_scope_privilege presence;
   sys_db_object accessible_from/caller_access diff. Core-table dampening: a
   configurable stop-list (sys_user, sys_user_group, sys_choice, cmdb_ci and
   kin) where closure records a DATA-PREREQUISITE finding instead of
   expanding the selection -- prevents closure balloon and consultant noise.
   Documented-gap register (in every runbook, verbatim): script-body
   references (dot-walks, hardcoded sys_ids), domain separation (sys_domain),
   legacy Workflow engine internals (wf_workflow activity/version closure
   beyond the record itself), notifications/email templates, REST/SOAP
   message + MID server + credential references, business-rule execution
   order. Each register item is a named v1.1+ candidate, not silent.
4. `nexus migrate preflight`: read-only probe of both instances for execution
   preconditions (CICD plugin, sn_cicd role, app-repo entitlement signal,
   auth mode), reported like diagnose-roles. Ships in MILESTONE 1 (read-only,
   fits the no-write charter posture). Also the natural home for spike S1
   logic.
5. Spike track (timeboxed, runs DURING the planner build, results due before
   any full-estate curation is invited): S0 closure scale + false-positive
   measurement AND lane-unit count measurement (validating the "tens to low
   hundreds of runbook units" feasibility claim) on the already-captured
   30K-artifact live dataset (first planner story, not optional); S1 CICD
   availability probe; S2 Update Source
   bootstrap + one retrieve/preview/commit round trip; S3 curated update-set
   packaging on OLD (sn_cdm probe first, companion scripted-REST app second);
   S4 import-set sys_id preservation empirics; S5 app-repo publish/install
   round trip + entitlement/auth reality. Rationale: parallel spikes close
   the "deferral pushes fatal discovery past commitment" risk -- lane
   viability is known before anyone curates thousands of rows against it.
6. Milestone-1 prerequisites (moved IN from the old executor-prereq list,
   because closure needs them): fix ConfigFetcher scalar fidelity (drops
   bool/number/null at capture) and build the selection-to-full-capture
   translation (checklist rows are name-only; closure walks reference
   values). ServiceNowClientProtocol update/delete surface remains a
   milestone-2 item.

## Trade-offs

| Option | Pro | Con | Position |
|--------|-----|-----|----------|
| Selection as plan file vs TUI vs CLI filters | Auditable, reviewable, replayable; git supplies merge/review | Less demo-flash than TUI | File (decided); TUI can layer later |
| Full dependency treatment vs warn-only vs block-only | Prevents silent breakage; waves enable ordering | Most planner work; needs waiver path to avoid deadlock | Full treatment + attributed waivers (decided, revised) |
| Milestone 1 = plan+runbook vs include app-repo lane | No platform write unknowns; immediate value | Curation effort could be partially invalidated if spikes kill a lane; no push-button execution yet | Plan+runbook (decided) WITH parallel spikes due before full-estate curation |
| Forward-fix vs lane-native rollback | Matches platform grain; re-assess is truth | Less automation on failure | Forward-fix (decided); revisit lane rollback in ADR-027 |
| Update-set packaging: sn_cdm vs companion app vs pre-existing sets only | sn_cdm = no footprint; companion app = general | sn_cdm unverified; companion app = installed footprint on customer instance | Defer to spike S3; prefer no-footprint if viable |
| Auth: pursue Basic-auth exception vs stay OAuth-pure | Exception unlocks sn_cicd lanes | Governance friction; contradicts OAuth-only posture | Surface via preflight; decide in ADR-027 with customer input |
| Closure expansion vs core-table dampening | Full expansion = maximal safety | Balloons through shared tables; noise burden | Dampen at stop-list tables into DATA-PREREQUISITE findings (revised) |

## Out of Scope (considered and rejected)

- Removing/deactivating anything on the NEW instance (no supported OAuth
  surface; exclusion = never-migrate by design).
- Fuzzy/semantic artifact matching (PRD-004 fence stands).
- Instance Data Replication (licensed, continuous, whole-table -- wrong shape
  for a curated one-time cutover).
- Script-body AST scanning in v1 -- in the documented-gap register instead.
- Any auto-apply without a human approval gate (charter hard limit 4).
- Whole-instance clone / clone excludes as mechanism (wrong direction and
  granularity).
- Tool-built plan-file merge/collaboration machinery (git + PR review is the
  collaboration model).

## Open Questions (NEEDS CLARIFICATION, max 3)

1. Closure scale and false-positive burden at 30K+ artifacts: does the v1
   closure stay computable (minutes, not hours) and reviewable (hundreds of
   findings, not tens of thousands) on the real dataset? Spike S0 answers
   before design freeze; core-table stop-list is the primary lever.
2. Approval/audit depth for a regulated customer: is a plan-file approval
   block + attributed waivers + journaled runbook provenance sufficient, or
   does the customer's change-management require external system integration
   (e.g. change requests referencing the plan)? PRD-005 must answer with
   customer input.
3. Update-set packaging on OLD: sn_cdm vs companion scripted-REST app vs
   pre-existing update sets only -- spike S3 decides; ADR-027 records it.
   (Customer preconditions and sys_id strategy remain tracked in the spike
   table S1/S4/S5 rather than occupying open-question slots.)

## Research Findings Appendix

### CICD Update Set API (record-level config lane)
- POST /api/sn_cicd/update_set/{create,retrieve,preview/{id},commit/{id},
  commitMultiple,back_out}; async, polled via links.progress; requires
  com.glide.continuousdelivery plugin + sn_cicd.sys_ci_automation role;
  commitMultiple is documented to commit in the order provided.
- Bypasses the sys_update_xml ACL because it drives the platform's own
  workers server-side (same classes as the UI buttons).
- Gaps: Update Source (sys_update_set_source) creation is Table-API-possible
  per a ServiceNow-employee community reply but deliberately undocumented;
  preview-problem response schema unverified; plugin availability per
  instance unverified.
- Source anchors: Zurich API reference bundle (cicd-update-set-api),
  ServiceNow/ServiceNowDocs GitHub mirror, community threads (July 2026
  Zurich thread on XML import automation). Full per-finding source URLs in
  the research workflow journal (wf_2fe96ce6-28f).
- Feeds: Recommendation 2 (ADR-027), spike S2, Key Insight 1.

### App Repository / sn_cicd app_repo (whole-app lane)
- POST /api/sn_cicd/app_repo/{publish,install,rollback} + batch install API
  (single rollback handle) + git sc/apply_changes alternative; same-company
  entitlement required; role sn_cicd.sys_ci_automation (community reports
  supplemental sys_app ACLs sometimes needed).
- Refuter verdict PARTIALLY_SUPPORTED: mechanism real; auth is Basic in
  practice (no documented OAuth; open feature request in ServiceNow/sdk#46);
  2026 policy requires Basic Auth Exception Account; app data (table rows)
  never moves -- config only; install may skip locally-modified records.
- Feeds: Recommendation 5 (spike S5), Key Insights 2 and 6.

### Data lane (Import Set / Table / Attachment / IRE)
- POST /api/now/import/{staging} + insertMultiple (chunk ~10K, 429/semaphore
  backoff); transform maps + coalesce = idempotent re-runs; OAuth supported
  with scoped Auth Scopes; Attachment API as separate per-record pass;
  journal fields do not migrate automatically; IRE
  (/api/now/identifyreconcile) for CMDB CIs with per-item INSERT/UPDATE audit.
- Refuter verdict PARTIALLY_SUPPORTED: declarative coalesce-on-sys_id does
  NOT preserve sys_ids on insert (sys_target_sys_id freshly allocated --
  convergent community reports); scripted onBefore setNewGuidValue is the
  workaround, unconfirmed across table types/domain separation; XML
  export/import preserves sys_ids but has no documented REST surface
  (upload.do is legacy/UI).
- Ordering forced by reference architecture: foundation (sys_user,
  sys_user_group, role join tables) -> config -> CMDB via IRE -> transactional.
- Feeds: Recommendation 5 (spike S4), Key Insight 5, milestone sequencing.

### Silent-breakage dependency taxonomy (the moat)
- Seven v1-covered classes, all silent in native tooling: dangling
  reference-field sys_ids; ACL rules vs sys_security_acl_role split;
  sysauto_script never auto-captured; sys_hub_flow -> snapshot -> subflow/
  action closure (no native tree report); sys_scope_privilege grants missing
  on target; sys_db_object accessible_from/caller_access posture drift;
  config-vs-data split (update sets never carry users/groups/CIs).
- Register of known-uncovered classes (documented in every runbook):
  script-body references, sys_domain separation, legacy Workflow internals,
  notifications/email templates, REST/SOAP messages + MID/credentials,
  business-rule execution order.
- Native tools checked and insufficient: update-set preview (batch-scoped
  only), Instance Scan (code quality, no dependency-completeness check),
  clone exclude/preserve (whole-table, wrong direction), sys_app
  Dependencies (opt-in, sparse on legacy instances).
- Feeds: Recommendation 3, Key Insight 4.

### Repo primitives inventory (reuse map)
- impact.fetch_cross_scope_refs: live 3-phase scan (sys_db_object ->
  sys_dictionary -> aggregate counts), keyed on bare scope strings -- works
  for custom scopes unmodified. fetch_scope_record_counts: per-table volume.
  reverse_dependencies: BFS with via-chains (plugin universe only; scale at
  30K+ unmeasured -- spike S0). SchemaDiscoverer: column-level reference/
  inheritance/relationship graph; bridge_subgraph for neighborhoods.
  /appmanager/dependencies: SN's own resolver as cross-check.
- Execution: PluginExecutor live-proven (install/activate/upgrade + gates +
  LIFO rollback); UpdateSetWriter wired but ACL-blocked; ApplyEngine skeleton
  unwired; execution/ package empty stubs; deactivate/uninstall structurally
  impossible over OAuth (server handler lacks methods; UI uses legacy
  session-cookie endpoint).
- Known fidelity bug (now a milestone-1 prerequisite): ConfigFetcher keeps
  only str and {value,display_value} fields -- drops bool/number/null at
  capture. Checklist listings are name-only; closure needs full captures.
- Mined catalog lead: sn_cdm (config-data export/upload, deployables,
  snapshot validate) -- unverified; catalog known-incomplete (sn_appclient's
  own working endpoints absent from it).
- Feeds: Recommendations 1, 3, 5 (S0), 6.

## Adversarial Review

Round 1 (13 challenges, 7 HIGH): accepted in full. Material changes -- the
two capture prerequisites moved into milestone 1 (closure walks reference
values); runbook unit-of-work redefined to lane-shaped units with a bounded
pilot; core-table stop-list/dampening added; taxonomy completeness register
added (domain separation, legacy Workflow, notifications, REST/MID/
credentials, BR order); approval/audit model promoted into PRD-005 scope;
hard block gained attributed waivers; plan freshness/--recheck semantics
added; LaneRoute demoted to a provisional advisory hint with schema_version,
binding lane architecture deferred to ADR-027; spike track gained S0 (closure
scale on the live 30K dataset) and a due-before-full-curation deadline; open
questions re-cut to closure scale, audit depth, and packaging.

Round 2 (8 challenges, 1 HIGH): VERDICT -- sound to proceed to PRD-005/
ADR-026 drafting, conditional on the PRD's approval/audit section explicitly
resolving items 1-2 below. Dispositions:
1. (HIGH, PRD-005 MUST resolve) Waiver segregation of duties: proposed
   default -- waiver approver must differ from plan author; engagement-repo
   branch protection (required reviewers) is a stated precondition, not an
   assumed fact. PRD-005 ratifies with customer change-management input.
2. (PRD-005 MUST resolve) DATA-PREREQUISITE enforcement: proposed default --
   such findings require an attributed acknowledgment entry in the plan file
   (same shape as waivers) before a plan is approvable; advisory-only is
   rejected.
3. (carried) Waiver risk-tiering: v1 treats all waivers uniformly as a
   deliberate simplification; PRD-005 states this and names a risk-class
   field as the v1.1 extension point.
4. (resolved in synthesis) Runbook staleness during manual execution: the
   runbook header carries generated-at, source snapshot identities, and an
   instruction block requiring `plan --recheck` within a stated validity
   window before executing any wave by hand.
5. (carried to ADR-027 + gap register) Data classification/PII handling for
   the data lane and for spikes against customer data -- explicitly deferred
   with reasoning, and spikes S2-S5 run on the demo pair, never on customer
   instances, until this is settled.
6. (resolved in synthesis) `migrate preflight` ships in milestone 1.
7. (resolved in synthesis) Lane-unit count measurement folded into spike S0.
8. (carried, PRD-005 question) Promotion tiers on the NEW side: PRD-005 must
   state whether NEW is a single target or a dev->test->prod chain; the plan
   model should not preclude a target-chain field.

## Session Notes

Assumptions mode. Researcher brief presented with two corrections (the
Uncategorized collapse and coverage bounds were fixed by the 2026-07-02
coverage-extension branch). Four Unclear items resolved by user to the
recommended options (plan file / full dependency treatment / plan+runbook
first milestone / stop+re-diff forward-fix). Customer-side preconditions kept
as spike items. Revision 1 incorporated all 13 adversarial challenges.
