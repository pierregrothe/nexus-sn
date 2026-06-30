# Brainstorming: NEXUS Replatform Checklist -- `nexus assess inventory` + `nexus assess migration`

Date: 2026-06-29
Mode: assumptions
Techniques: assumptions-mode (codebase recon -> user framing confirmation -> 2x adversarial pass -> verification)

## Context Brief

Project: NEXUS Python 3.14 ServiceNow architect CLI. New backlog
candidate driven by a real customer pattern (acquisition closed,
replatforming onto a fresh "clean" instance): produce a per-domain
checklist of the use cases and workflows on the OLD instance, with
each item auto-ticked as it is built on the NEW instance. The team
re-runs it through the migration to watch the TODO set shrink.

What exists today (Confident, verified):

* `nexus.capture` layer shipped. `ScopeManifest` / `ScopeEntry`
  (scope discovery) and `CaptureResult` (frozen+strict,
  `tuple[ConfigRecord, ...]`, `by_table()` grouping) --
  `src/nexus/capture/models.py:41-98`. CRITICAL detail verified:
  `CaptureResult.table_group: str` is singular, but the one shipped
  group `AI_AUTOMATION` (`src/nexus/capture/tables.py:66-97`) bundles
  ALL artifact tables together -- `ai_skill`, `sys_hub_flow` (+inputs/
  logic), `sys_hub_action_type_definition`,
  `virtual_agent_conversation_topic` (+blocks), `sys_ai_agent`. So one
  capture over N scopes (`CaptureResult.scope_ids: tuple[str, ...]`)
  already contains every artifact type the classifier needs.
* `TableSpec.key_fields` defaults to `("sys_id", "name", "sys_scope")`
  (`tables.py:48`), so each `ConfigRecord.fields` carries `name`, and
  the artifact `type` is just `ConfigRecord.table`. `WorkflowRef.name`
  and `.type` are therefore extractable today.
* `nexus.plugins.diff` -- proven cross-instance comparison spine:
  `compute_diff(...) -> PluginDiff` + `project_to_promote_plan(...) ->
  PromotionPlan`, pure functions over two loaded inventories
  (`src/nexus/plugins/diff.py:121-243`). Matches on the canonical
  `plugin_id`.
* `nexus.plugins.drift` -- proven status-bearing diff:
  `compute_drift(...) -> PluginDriftReport` with `added | removed |
  version_changed | state_changed` (`src/nexus/plugins/drift.py:79-112`).
  The model for status-per-item.
* `nexus assess` is BUILT, not a stub. It exposes `run_assess()` as a
  PLAIN CALLABLE invoked from `commands_top.py` -- there is no Typer
  app object for `assess` today (`src/nexus/cli/commands_assess.py`).
  The orphan files `assessment/readiness.py` + `assessment/scanner.py`
  are dead stubs superseded by `gates.py`/`report.py`/`reporter.py`.
* `InstanceRegistry` stores per-profile `meta.json`, `snapshot.json`,
  `plugins.json`, baselines under `~/.nexus/instances/<profile>/`
  (`src/nexus/instances/registry.py`). Two instances + their captures
  are available today.
* Schema product catalog shipped (PR #54): GitHub-synced
  `products.json` mapping families/acronyms to scopes; plugins carry a
  curated `PluginInfo.product_family` with an `Uncategorized` fallback.
* 8 domain specialists exist as files under
  `src/nexus/agents/specialists/` but are 2026.07 [planned], NOT wired
  (`.primer/roadmap.md:107-111`).

## Confirmed assumptions (user framing resolved)

* **Bi-directional from day one.** v1 connects to BOTH instances,
  inventories each, diffs, and the checklist auto-ticks items already
  present on the target.
* **Lives under `nexus assess`** (user chose the namespace over a new
  `replatform`/`blueprint` verb).
* **Reusable `nexus assess inventory <profile>` ships as a first-class
  subcommand**, not just an internal helper.
* **v1 = deterministic classification; AI enrichment = v2** (depends on
  the 2026.07 Agent Specialists epic).

## Hard project constraints

* Pydantic frozen+strict+extra=forbid
* Python 3.14 syntax (PEP 758, PEP 695, match/case with `case _:`);
  absolute imports only
* No mocks (fakes only, `tests/fakes/`)
* File-size caps ADR-023: src/ 800, tests/ 1400
* 100% line coverage, mypy strict + pyright strict, ruff 0,
  no `# type: ignore`
* Layer order: capture/connectors -> (new) replatform analysis -> cli

## Key Insights

1. **This is NOT "fill in the assess stub."** The shipped `assess` is a
   single-instance declarative rule-engine gate validator. `PRD-002`
   explicitly fences out "Cross-instance comparison -- one capture, one
   assessment" and "Assessment history / time-series" -- the two things
   this feature needs. The replatform checklist is a NEW capability that
   shares the `assess` namespace by user choice and must NOT couple to
   the RuleEngine.

2. **The implementation is the plugins diff/drift shape, one altitude
   up.** `MigrationChecklist` is the domain-level analog of
   `PromotionPlan` + `PluginDriftReport`: capture two inventories, run a
   pure diff, emit a status-bearing report.

3. **Cross-instance identity uses a normalized natural key, never
   sys_id** -- a fresh instance reassigns every sys_id. The key is
   `(technical_scope_key, type, normalized_name)`, where the scope key
   comes from `ScopeEntry.scope` (the diff cannot use `ConfigRecord.
   scope_name`, a localizable display string, nor `scope_sys_id`, which
   differs across instances). This makes `ScopeManifest` a REQUIRED
   classifier input, and the normalization rule load-bearing v1 scope
   (not deferrable).

4. **Classification is deterministic in v1**, mirroring the byte-stable
   `--grouped` ERD: catalog + `product_family` + captured scope bucket
   artifacts into product-family use cases with zero LLM. BUT a custom
   scope (`x_acme_hr_ext`) has no catalog entry and collapses to
   `Uncategorized`; for a customer-heavy instance that can be MOST of
   the inventory. v1 is buildable and honest, but coarse for custom
   estates until the 2026.07 specialists add naming/sub-clustering (v2).

5. **Fidelity is bounded by capture coverage, and an empty checklist is
   the dangerous failure mode.** `capture discover` only surfaces scopes
   with custom AI/automation config; a pure-OOB ITSM/CSM deployment with
   no custom flows yields ZERO inventory items and a clean checklist.
   No business rules, script includes, ACLs, or scheduled jobs until the
   `DEVELOPER_PLATFORM` capture extension lands (`roadmap.md:165`). The
   reporter MUST emit a prominent Notice when source inventory is empty
   or thin -- "clean checklist != nothing to migrate."

6. **Advisory only -- it reports, it never builds.** Same stance as
   `assess` ("gates report; they never act"). No `--apply`, no update-set
   generation on the target; that is `nexus capture push` + a future
   ApplyEngine. Conflating them re-opens the PRD-002 `--fix` scope-creep
   trap one altitude up.

## Recommendations (build sequence)

1. **New package `src/nexus/replatform/` -- separate from
   `assessment/`.** The CLI namespace (under `assess`) is independent of
   code organization; keeping the analysis layer out of the rule-engine
   package preserves the layer boundary and the size caps.

2. **`models.py` -- frozen+strict+extra=forbid:**
   * `WorkflowRef` -- `key` (the normalized natural key), `name`,
     `type` (source table: `sys_hub_flow` | `ai_skill` |
     `virtual_agent_conversation_topic` | ...), `scope` (technical key).
   * `UseCase` -- `key`, `name`, `domain` (product family or
     `Uncategorized`), `workflows: tuple[WorkflowRef, ...]`,
     `evidence: tuple[str, ...]` (scopes/plugins justifying it).
   * `UseCaseInventory` -- `profile`, `captured_at`,
     `coverage: tuple[str, ...]` (table groups that fed it),
     `use_cases: tuple[UseCase, ...]`.
   * `ChecklistItem` -- `use_case_key`, `kind` (use_case | workflow),
     `status` (TODO | DONE | PARTIAL | EXTRA), and for `kind=use_case`
     a `built_count` / `total_count` so PARTIAL carries an actionable
     fraction ("12/30 built"), not a near-constant boolean.
   * `MigrationChecklist` -- `source_profile`, `target_profile`,
     `source_captured_at`, `target_captured_at`, `coverage`,
     `items: tuple[ChecklistItem, ...]` in stable `(domain, key)` order.

3. **`classifier.py` -- pure fn**
   `classify(captures: tuple[CaptureResult, ...], scopes: ScopeManifest,
   plugin_inventory: PluginInventory, catalog: ProductCatalog) ->
   UseCaseInventory`. Plural `captures` for forward-compat with future
   table groups (one CaptureResult suffices for v1's `AI_AUTOMATION`).
   `scopes` resolves each `ConfigRecord.scope_sys_id` to its technical
   `ScopeEntry.scope` for the key. No I/O, no LLM, NO MCP.

4. **Natural-key normalization -- pinned v1 algorithm (NOT deferred):**
   `key = f"{scope}|{type}|{norm(name)}"` where `scope = ScopeEntry.
   scope`, `type = ConfigRecord.table`, and `norm(name) = name.
   casefold()` with internal whitespace collapsed and stripped. One
   grouping boundary decision: a scope's workflows attach to exactly one
   `UseCase` (its family bucket); multiple scopes can feed the same
   family. Display-name localization and copy-then-rename remain known
   mismatch sources (see Open Questions).

5. **`diff.py` -- pure fn** `build_checklist(source, target) ->
   MigrationChecklist`, the analog of `compute_drift`. Status is
   computed at the WORKFLOW grain first:
   * in source, absent in target -> `TODO`
   * in both -> `DONE`
   * in target, absent in source -> `EXTRA` (informational)
   The use-case rolls up: all workflows DONE -> `DONE`; none -> `TODO`;
   some -> `PARTIAL` with `built_count/total_count`. Matches on the
   normalized key only.

6. **`reporter.py` -- reuse `ui/components/`** (`DataTable`,
   `KeyValuePanel`, `StatusBadge`, `Notice`) for console. A markdown
   emitter for `--out checklist.md` is a SEPARATE, counted unit (its own
   module + tests), not free. MUST emit a prominent empty/thin-coverage
   Notice. Mirrors `nexus plugins advisories` rendering.

7. **`enrichment.py` -- v2 only, behind a protocol.** AI use-case naming
   + sub-clustering + gap narration via the specialists. Faked in tests.
   Off the v1 critical path; depends on 2026.07.

8. **CLI: restructure `assess` into a Typer command group.** Today
   `assess` has no Typer app -- `commands_top.py` calls `run_assess()`
   directly; `commands_top.py` is therefore a named build target. The
   restructure needs (a) a `nexus assess` Typer sub-app, (b) a group
   callback with `invoke_without_command=True` AND an explicit
   `if ctx.invoked_subcommand is None:` guard so the bare-gate/health
   path runs ONLY when no subcommand is given (else `assess inventory`
   double-fires), (c) a `ReplatformCollaborators` bundle reaching the
   `inventory`/`migration` callbacks via the Typer context object
   (`ctx.obj`), since the plain-arg threading used by `run_assess` does
   not reach group subcommands. Runtime behavior of bare `assess` is
   preserved; the `--help`/completion tree changes (group, not leaf).
   New subcommands:
   * `nexus assess inventory <profile> [--from-archive P] [--out inv.json]`
   * `nexus assess migration --from <old> --to <new> [--from-archive P]
     [--to-archive P] [--scope-alias OLD=NEW ...] [--out checklist.md]`

9. **Fakes in `tests/fakes/`:** `FakeUseCaseInventory`,
   `FakeScopeManifest`, and `FakeCaptureResult` records that inject a
   `name` field so the classifier can build `WorkflowRef`s. No mocks.

## Trade-offs

| Option | Pro | Con | Position |
|---|---|---|---|
| Bi-directional v1 (diff old vs new) | Auto-tick; answers "what's left" | Needs two captures + natural-key matching | Pick (user choice) |
| Live under `nexus assess` | Reuses namespace | Crosses PRD-002 cross-instance fence; forces leaf->group rewrite | Pick (user choice); amend PRD-002 |
| New `nexus replatform` verb | Clean separation; no group rewrite | New top-level surface | Rejected by user |
| Separate `src/nexus/replatform/` package | Clean boundary; respects size caps | One more package | Pick |
| Deterministic classification v1 | Testable; LLM-free; ships now | Custom scopes collapse to Uncategorized | Pick; AI enrichment = v2 |
| Match on `(scope, type, name)` natural key | Survives fresh sys_ids | Scope/flow rename reads as TODO+EXTRA | Pick; `--scope-alias` mitigates; document |
| Match on sys_id | Exact | Breaks across instances | Reject |
| Status at workflow grain, fraction rollup | PARTIAL is actionable (12/30) | Slightly more model | Pick |
| Status at family grain only | Simpler | PARTIAL near-constant, uninformative | Reject (adversarial hit) |
| Advisory only (report) | Mirrors assess; safe | User acts manually | Pick |
| `--apply` build on target | One-shot | Re-opens `--fix` creep; ownership is capture/ApplyEngine | Reject |

## Out of Scope (explicit anti-creep fence)

* **Auto-build on the target (`--apply` / update-set generation).** The
  checklist reports; building is `nexus capture push` + future ApplyEngine.
* **Any MCP / live ServiceNow query inside the replatform analysis
  layer.** `classify` and `build_checklist` consume `CaptureResult` +
  `ScopeManifest` + `PluginInventory` only -- mirrors PRD-002's
  "rules consume CaptureResult only" fence.
* **AI classification/enrichment in v1.** Deterministic only; enrichment
  is v2 on the 2026.07 specialists.
* **Capture coverage beyond what ships today.** No business rules,
  script includes, ACLs, scheduled jobs until the `DEVELOPER_PLATFORM`
  extension. v1 covers the `AI_AUTOMATION` group + plugins.
* **A curated global use-case taxonomy.** v1 buckets by product family;
  finer taxonomy waits on specialists.
* **Scoring / weighting / "% migrated" headline number.** Per-item
  status + per-use-case fraction only; no aggregate score.
* **Time-series / migration history.** A checklist is point-in-time;
  re-run to refresh. No stored timeline.
* **Touching shipped gate/RuleEngine semantics.** Bare `assess` /
  `--for` / `--job` behavior is unchanged.
* **Field-level diff of a workflow's internals.** v1 diffs
  presence/absence at the use-case + workflow grain.
* **Fuzzy matching of renamed-and-modified workflows.** v1 uses exact
  normalized-key match plus the explicit `--scope-alias` map; semantic
  similarity matching is out.

## Open Questions

1. **Scope/flow rename during replatform** (the acquisition case:
   `x_oldcorp_app` -> `x_newcorp_app`) makes every item mismatch as
   TODO+EXTRA. v1 mitigation: explicit `--scope-alias OLD=NEW`
   (repeatable), applied to the target side before matching. Confirm at
   epic whether a name-level alias is also needed.
2. **Markdown emitter: v1 story or v2?** It is counted, non-trivial
   output code. Recommend v1 (the checklist is the deliverable) as its
   own story; confirm.
3. **Use-case granularity.** v1 = one product family = one UseCase.
   Revisit when specialists can sub-cluster a 30-flow ITSM scope.
4. **`PRD-00X` promotion.** On promotion this needs its own PRD + epic
   and a one-line PRD-002 amendment recording that `assess` now spans
   single-instance gates AND cross-instance migration.

## Adversarial Review

Two Read-only passes (sonnet), distinct lenses, run against this doc +
the shipped code. Both returned "not ready to act on as written"; all
findings are resolved above. One reviewer blocker was a misread that
verification overturned.

Pass A (scope / collision / Typer):
* BLOCKER -- assess has no Typer app; leaf->group conversion is an
  unspecified structural rewrite and `invoke_without_command` needs an
  `invoked_subcommand` guard or the bare path double-fires. RESOLVED:
  Rec 8 specifies the guard, the `ctx.obj` collaborator path, and names
  `commands_top.py` as a build target.
* BLOCKER -- natural-key normalization deferred but is the core v1
  algorithm. RESOLVED: Rec 4 pins it into v1 scope.
* CONCERN -- markdown emitter presented as free. RESOLVED: Rec 6 +
  Open Q2 count it as a separate unit.
* CONCERN -- no-MCP fence missing. RESOLVED: added to Out of Scope.
* CONCERN -- PARTIAL near-constant at family grain. RESOLVED: Rec 5
  computes status at workflow grain with a built/total rollup.
* NIT -- "UX preserved unchanged" overstated. RESOLVED: Rec 8 scopes the
  claim to runtime behavior; --help/completion tree changes.

Pass B (feasibility / data / dependencies):
* BLOCKER (OVERTURNED) -- "single CaptureResult cannot feed the
  classifier; flows/skills/topics are separate table groups." Verified
  FALSE against `capture/tables.py:66-97`: `AI_AUTOMATION` bundles all
  artifact tables in one group, so one CaptureResult covers them.
  Downgraded to a signature note -- Rec 3 still takes
  `tuple[CaptureResult, ...]` for forward-compat, not necessity.
* BLOCKER -- `ConfigRecord` lacks the technical scope key; it lives in
  `ScopeEntry.scope` via `ScopeManifest`. RESOLVED: Rec 3 adds
  `ScopeManifest` to the signature; Rec 4 builds the key from it.
* CONCERN -- custom scopes collapse to Uncategorized. RESOLVED:
  Insight 4 states the limitation honestly; specialists (v2) address it.
* CONCERN -- scope rename -> wrong TODO+EXTRA. RESOLVED: Open Q1 +
  `--scope-alias`.
* CONCERN -- empty checklist false-safety. RESOLVED: Insight 5 + Rec 6
  require a prominent empty/thin-coverage Notice.
* NIT -- fakes must inject `name` fields; scope->UseCase grouping
  boundary. RESOLVED: Rec 9 + Rec 4.

No remaining blockers at synthesis level. Story-level ambiguities
(exact Typer app location, alias semantics) surface at epic decomposition.

## Dependencies

* Instance registry + capture (`ScopeManifest`, `CaptureResult`,
  ArchiveReader) -- shipped.
* Schema product catalog + `PluginInfo.product_family` -- shipped.
* Plugin inventory (`plugins.json`) -- shipped.
* `ui/components/` rendering primitives -- shipped.
* `commands_top.py` + a new `assess` Typer group -- build target.
* AI enrichment -> 2026.07 Agent Specialists -- planned (v2 only).
* PRD-002 amendment on promotion (cross-instance fence lifted for the
  migration subcommand only).
