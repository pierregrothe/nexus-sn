# Decision Log

Append-only record of architectural and design decisions.

## Template

```
### YYYY-MM-DD -- [Title]

**Status:** proposed | accepted | superseded by [link]

**Context:** Why this decision was needed.

**Decision:** What was decided.

**Consequences:** What follows from this decision.
```

## Compressed entries (2026-05-07 through 2026-05-09)

Older entries trimmed on 2026-05-19 sync per >150-line cap. Full text
lives in git history at commit `592d525` and earlier.

* 2026-05-07 -- **API-direct architecture (original intent)**: superseded
  by ADR-015. Original plan to call Anthropic API directly was 429-gated;
  claude-agent-sdk subprocess path adopted instead.
* 2026-05-07 -- **Template distribution via GitHub sync**: templates live
  in the same repo under `templates/`; `nexus sync` is a required first
  step after install; offline use requires a prior sync.
* 2026-05-07 -- **Assessment 3-gate model**: Gate 1 readiness + Gate 2
  validation + standalone `nexus assess`; RuleEngine stateless and
  re-runnable; rollback scoped to execution layer.
* 2026-05-07 -- **CalVer versioning (YYYY.0M.PATCH)**: freshness over API
  stability signaling; patch resets monthly; no automated bumping.
* 2026-05-07 -- **Connector plugin system**: ConnectorProtocol +
  ConnectorRegistry; ServiceNow REST built-in; future connectors register
  themselves without core code changes.
* 2026-05-07 -- **Sprint retrospective governance upgrade**: 8 new ADRs
  (006-013) document governance improvements; 10 blocking pre-edit rules
  + coverage ratchet + pyright strict + lean CI introduced.
* 2026-05-07 -- **Pluggable AuthProvider with OAuth-first chain**:
  superseded by ADR-015. OAuth path 429-gated at /v1/messages forced the
  Agent SDK migration; AuthProvider abstraction deleted entirely.
* 2026-05-08 -- **Migrate from anthropic SDK to claude-agent-sdk**:
  Claude Code CLI >= 2.0.0 became a hard runtime dependency; auth chain
  delegated to the SDK; subprocess overhead per call (500ms-30s).
* 2026-05-08 -- **Single canonical caching decorator (@cached, ADR-017)**:
  Layer-0 `src/nexus/cache/` with diskcache backend; Semgrep rules +
  runtime checks enforce the contract; persist mode lazy-resolves backend
  for test isolation.
* 2026-05-08 -- **Tier detection from Claude Code OAuth (ADR-018)**:
  Tier enum + TierDetector reading OAuth subscription claim +
  claudeAiMcpEverConnected list + needs-auth cache; no live MCP probing
  yet.
* 2026-05-08 -- **Lessons from /simplify reviews (ADR-019)**:
  ExternalKeychainClient wrapper for cross-app reads; @cached lazy-resolve
  fix; 3 new Semgrep rules; PR template gates /simplify execution.
* 2026-05-08 -- **NEXUS auto-update from GitHub Releases (ADR-020)**:
  `src/nexus/updater/` checks GitHub Releases every launch (3s timeout);
  pip install + os.execv re-run; NEXUS_AUTO_UPDATE=0 escape hatch.
* 2026-05-08 -- **OAuth auto-provisioning via caller-supplied
  client_secret**: `_provision_oauth()` POSTs to oauth_entity with
  Basic auth + UUID4 secret; falls back to manual 3-step guide on
  failure; PDI token cap remains 30 min.
* 2026-05-09 -- **ServiceNowClientProtocol for DI in capture layer**:
  Protocol typed with `dict[str, object]` returns; FakeServiceNowClient
  satisfies it structurally without inheriting from the concrete class.

---

## Compressed entries (2026-05-13 through 2026-05-19)

Trimmed on the 2026-07-04 sync per the >150-line cap. Full text lives in
git history.

* 2026-05-13 -- **README sync via injectable-runner script**: scripts/sync_readme.py auto-updates README version/Python-req/test-count during /primer sync.
* 2026-05-13 -- **Plugin execution full lifecycle (M+N)**: install/activate/upgrade/apply-plan with rollback + deactivate/uninstall with mandatory impact gate.
* 2026-05-13 -- **README Gantt synced from roadmap.md** via sync_readme.py between HTML anchors.
* 2026-05-13 -- **README badge row synced from live project data** (Python version, test count, LOC).
* 2026-05-14 -- **Plugin deactivate/uninstall is SN-platform-blocked**: no programmatic API exists; CLI stays a forward-compatible stub.
* 2026-05-14 -- **Batch plugin upgrade + governance ADRs**: ADR-021 (@model_validator over @computed_field), ADR-022 (cli.py deferred imports), black joined the post-edit hook.
* 2026-05-15 -- **Exhaustive smoke coverage for plugins updates** (6->16 permutations) + tests/ type-check cleanup.
* 2026-05-16 -- **Brew/apt-style plugin CLI redesign**: split into read-only `outdated` + destructive `upgrade`; transparent OAuth refresh; SN "already installed" 400 = idempotent success.
* 2026-05-18 -- **Offering-plugin install structurally unreachable via OAuth/REST** (AppUpgradeAjaxProcessor is AJAX-only); documented unsupported.
* 2026-05-18 -- **PromptSource Protocol for testable wizard flows** (no unittest.mock).
* 2026-05-18 -- **Wire vs cached manifest model split** fixes an extra="forbid" round-trip break.
* 2026-05-18 -- **Idempotent provision_oauth** on a deterministic nexus-<profile> name (GET-then-PATCH-rotate).
* 2026-05-19 -- **FramedViewer (Textual) supersedes pypager** for sticky-frame paging (ADR-024); pypager deleted as dead code.
* 2026-05-19 -- **BatchProgressProtocol** with adaptive RICH/PLAIN implementations.
* 2026-05-19 -- **Drop --cov-fail-under=100** in favour of the per-file .ratchet.json ratchet.
* 2026-05-19 -- **2026.06 phase closed** (Assessment + Template Library shipped end-to-end; tests 1367->1624, PRDs 1->3).
* 2026-05-19 -- **sys_update_xml ACL block on live PDIs**: SN blocks direct REST POST even for admin; bundle-via-update-set deferred to a v2 direct-write/import-API follow-up.

---

### 2026-06-29 -- Project charter created (charter.md)

**Status:** accepted

**Context:** PRD-002 and PRD-003 carried `charter_link: charter.md` but no
charter file ever existed -- a dangling governance reference. Promoting the
replatform-checklist feature to a milestone surfaced the gap (the primer PRD
flow guards on a charter).

**Decision:** Author `.primer/charter.md` from brief.md / product.md / CLAUDE.md
and the fences already implied by the ADRs/PRDs. Seven Hard Product Limits
(NEVER) confirmed by the user: no Claude Code/Desktop/Node.js dependency; never
hosts an MCP server; no secrets in config files; no instance mutation without a
human approval checkpoint (assessment/diff/analysis layers are advisory); no
self-modification without a validation gate; no install-time static knowledge;
no hardcoded product/license/scope specifics.

**Consequences:** Every future PRD anchors to a real charter section. The
dangling `charter_link` references in PRD-002/003 now resolve. Charter is
user-owned; sync never overwrites it.

---

### 2026-06-29 -- Replatform checklist promoted to 2026.07 (ADR-025, PRD-004)

**Status:** accepted

**Context:** A customer replatform (acquisition onto a clean instance) needs a
bi-directional use-case/workflow checklist comparing two instances. The shipped
`nexus assess` is a single-instance gate validator and PRD-002 explicitly fences
out cross-instance comparison, so this is a new capability, not a stub fill-in.
Scoped in `.primer/brainstorming/2026-06-29-nexus-assess-migration.md` and
hardened by a 2x adversarial pass (which overturned one false blocker about
CaptureResult.table_group and pinned the ScopeManifest requirement + natural-key
normalization).

**Decision:** New `src/nexus/replatform/` package (separate from the rule-engine),
consuming CaptureResult + ScopeManifest + PluginInventory. Cross-instance identity
uses a normalized `(scope, type, name)` natural key, never sys_id. Surfaced under
`nexus assess` (converted leaf->group, gate behavior preserved) as `inventory` +
`migration` subcommands. Advisory only; deterministic v1; AI enrichment is v2 on
the 2026.07 specialists. Recorded as ADR-025 + PRD-004 + epic
`2026.07-nexus-replatform-checklist` (6 stories). PRD-002's cross-instance fence
is consciously lifted for `assess migration` only (gate semantics unchanged).

**Consequences:** assess now spans single-instance gates AND cross-instance
migration. Fidelity is bounded by current capture coverage (AI_AUTOMATION group);
the reporter flags empty/thin coverage so a clean checklist is never misread.
First story: `01-replatform-models`.

## 2026-07-02: Replatform coverage extension -- deterministic breadth before AI depth

Closed the v1 coverage gaps on branch feat/2026.07-replatform-coverage
(plan: docs/superpowers/plans/2026-07-01-replatform-gap-closure.md):

- Multiset natural-key matching in the checklist diff: duplicate
  (scope|table|name) keys consume target occurrences one-for-one; unconsumed
  targets each surface as EXTRA. Chosen over key-uniquification because
  duplicates are matching-equivalent; proven live (AICTJobManager 2v1 ->
  1 DONE + 1 TODO).
- DEVELOPER_PLATFORM table group (sys_script, sys_script_include,
  sys_script_client, sys_ui_policy, sys_ui_action, sys_security_acl,
  sysauto_script, wf_workflow) via new TableSpec.name_field; registry
  addition is non-breaking (capture engine/CLI pin ai_automation defaults).
- Global scope: second per-table pass filtered by sys_customer_update=true.
  ServiceNow gives each global app its own sys_scope row, so global apps
  group under their display names for free.
- Per-app use-case naming: catalog product > app display name >
  Uncategorized (unresolvable only). --domain-map YAML overlay for
  engagement-supplied business domains; deliberate deterministic bridge
  until agent-specialists lands AI enrichment.
- Honesty rails: absent tables warned per side (UseCaseInventory.
  skipped_tables), unnamed artifacts counted + warned.
- PEP 758 caveat learned: unparenthesized multi-except cannot carry `as`;
  parenthesized form required when binding.

---

### 2026-07-04 -- Governance registry gate wired + kind-aware orphan detection

**Status:** accepted

**Context:** The policy registry (.primer/policies/registry.yaml) had an
installed drift checker (.claude/scripts/primer-reconcile.py) that was never
wired into pre-commit, so registry<->config drift did not gate commits.
Adversarial verification (20 synthetic drift fixtures) also surfaced two
checker defects: a 136-line ORPHANED-CHECK flood on the per-module coverage
ratchet, and a kind-agnostic `claimed` set that let a live pre-commit hook be
masked by a same-string check of a different kind.

**Decision:** Wire primer-reconcile as a pre-commit hook, registered as the
`governance-reconciliation` policy (gates-blocking). Exclude per-check
`baseline_path` override baselines from the orphan scan (kills the flood;
override keys are project DATA, not a governance surface). Make orphan
detection kind-aware via separate `claimed_pc` / `claimed_ratchet` sets. Both
checker fixes carried in the global primer skill template.

**Consequences:** Commits gate on registry drift once `pre-commit install` is
run (the hook is not installed by default in this checkout). The
governance-reconciliation policy makes the registry self-consistent (the gate
claims its own hook). Verified: 15/16 adversarial fixtures pass, the 16th being
the pre-existing cross-kind bug now fixed.
