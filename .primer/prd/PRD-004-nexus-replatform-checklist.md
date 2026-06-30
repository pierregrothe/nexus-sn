---
id: PRD-004
title: NEXUS Replatform Checklist -- nexus assess inventory + migration
status: draft
date: 2026-06-29
adrs: [ADR-025, ADR-003]
charter_link: charter.md#3-hard-product-limits
milestone: 2026.07-replatform-checklist
---

# PRD-004: NEXUS Replatform Checklist -- `nexus assess inventory` + `nexus assess migration`

## Problem

Customers replatforming onto a fresh "clean" ServiceNow instance (e.g.
after an acquisition closes) have no fast way to see which use cases and
workflows from the OLD instance still need to be built on the NEW one.
NEXUS can already capture config, diff plugin inventories, and assess a
single instance against rules, but it cannot compare two instances at the
use-case grain or emit an actionable build checklist. This PRD ships that
capability as two subcommands under `nexus assess`.

## Users

* Solution Consultants / architects driving a replatform who need a
  per-domain checklist that auto-ticks as the new instance is built.
* Customers and partners tracking migration progress across re-runs.
* Internal NEXUS users who want a reusable single-instance use-case
  inventory (`nexus assess inventory`) as a building block.

## In Scope (must-haves)

* **`src/nexus/replatform/` package**, separate from `assessment/` (the
  rule-engine), per ADR-025. Frozen+strict+extra=forbid models:
  `WorkflowRef`, `UseCase`, `UseCaseInventory`, `ChecklistItem`,
  `MigrationChecklist`.
* **Deterministic classifier** -- pure
  `classify(captures: tuple[CaptureResult, ...], scopes: ScopeManifest,
  plugin_inventory: PluginInventory, catalog: ProductCatalog) ->
  UseCaseInventory`. Buckets captured artifacts into product-family use
  cases. No I/O, no LLM, no MCP. `ScopeManifest` supplies the technical
  scope key for the natural key.
* **Pinned natural-key normalization** --
  `key = f"{scope}|{type}|{casefold(collapse_ws(name))}"`, where
  `scope = ScopeEntry.scope`, `type = ConfigRecord.table`. Never sys_id.
* **Bi-directional diff** -- pure `build_checklist(source, target) ->
  MigrationChecklist`. Status at the workflow grain: `TODO` (source only),
  `DONE` (both), `EXTRA` (target only). Use cases roll up to `DONE` / `TODO`
  / `PARTIAL` with a `built_count` / `total_count` fraction.
* **`--scope-alias OLD=NEW`** (repeatable) on `migration` to line up scopes
  renamed during a replatform before matching.
* **Reporter** reusing `ui/components/` (`DataTable`, `KeyValuePanel`,
  `StatusBadge`, `Notice`) for console, plus a markdown emitter for
  `--out checklist.md`. MUST emit a prominent Notice when the source
  inventory is empty or thin.
* **CLI** -- `assess` converted to a Typer group (preserving bare
  gate/health behavior behind an `invoke_without_command` guard):
  `nexus assess inventory <profile> [--from-archive P] [--out inv.json]`
  and `nexus assess migration --from <old> --to <new> [--from-archive P]
  [--to-archive P] [--scope-alias OLD=NEW ...] [--out checklist.md]`.
* **Fakes in `tests/fakes/`**: `FakeUseCaseInventory`, `FakeScopeManifest`,
  and `FakeCaptureResult` records injecting a `name` field. No mocks.

## Out of Scope (anti-creep fence -- the load-bearing section)

* **Auto-build on the target** (`--apply` / update-set generation). The
  checklist reports; building is `nexus capture push` + a future ApplyEngine.
* **AI classification / enrichment in v1.** Deterministic only; enrichment
  (specialist-driven naming + sub-clustering) is v2 on the 2026.07 specialists.
* **Capture coverage beyond what ships today.** No business rules, script
  includes, ACLs, or scheduled jobs until the `DEVELOPER_PLATFORM` capture
  extension lands. v1 covers the `AI_AUTOMATION` group + plugins.
* **A curated global use-case taxonomy.** v1 buckets by product family;
  finer taxonomy waits on the specialists.
* **Scoring / weighting / "% migrated" headline number.** Per-item status +
  per-use-case fraction only.
* **Time-series / migration history.** A checklist is point-in-time; re-run
  to refresh. No stored timeline.
* **Touching the shipped gate / RuleEngine semantics.** Bare `assess` /
  `--for` / `--job` behavior is unchanged.
* **Field-level diff of a workflow's internals.** v1 diffs presence/absence
  at the use-case + workflow grain.
* **Fuzzy matching of renamed-and-modified workflows.** Exact normalized-key
  match plus the explicit `--scope-alias` map only.
* **MCP / live queries inside the replatform layer.** Captured data only.

## Acceptance Criteria

- [ ] `replatform/` models frozen+strict+extra=forbid; pyright + mypy strict
  0 errors; 100% line coverage.
- [ ] `classify(...)` pure; tests cover empty capture, custom scope ->
  Uncategorized, multi-scope, and `WorkflowRef` extraction from `fields`.
- [ ] Natural-key normalization tested for case, whitespace, and
  cross-instance (different sys_ids, same key) equality.
- [ ] `build_checklist(...)` emits correct TODO / DONE / EXTRA at workflow
  grain and DONE / TODO / PARTIAL(built/total) at use-case grain; tests
  cover each transition and a scope-alias remap.
- [ ] Reporter renders console via `ui/components/` only and writes
  `--out checklist.md`; emits the empty/thin-coverage Notice on a zero-item
  source inventory.
- [ ] `nexus assess inventory <profile>` and `nexus assess migration --from
  --to` functional end-to-end against fakes; bare `nexus assess` /
  `--for` / `--job` behavior unchanged (regression test).
- [ ] All new modules conform to ADR-023 size caps (src/ 800, tests/ 1400).

## Success Metrics

* On a real replatform (alectri-class data), `assess migration` produces a
  checklist whose TODO count shrinks across re-runs as the target is built.
* `assess inventory` is reused by `migration` without duplication (one
  classifier path).
* Zero false `DONE` from sys_id collisions (natural-key match verified).
* The empty/thin-coverage Notice fires on an OOB-only source so no team
  misreads a clean checklist as "nothing to migrate."

## Dependencies

* **ADR-025** -- replatform analysis layer + natural-key matching (this PRD).
* **ADR-003** -- 3-gate assessment model (extended, not modified).
* **Capture layer** -- `CaptureResult`, `ScopeManifest`, `ArchiveReader`
  (shipped).
* **Schema product catalog** + `PluginInfo.product_family` (shipped).
* **Plugin inventory** (`plugins.json`) + **InstanceRegistry** (shipped).
* **ui/components** (shipped).
* **AI enrichment** -> 2026.07 Agent Specialists (v2 only).

## Out of Library Scope (always)

Replatform ships as part of the NEXUS CLI; no separate library. The runtime
still owns: MCP probing (capabilities layer), OAuth (auth layer), HTTP
transport (connectors layer), and console primitives (ui/components). The
replatform layer depends on but does not duplicate any of these, and never
queries ServiceNow directly.

## Open Questions

* `--scope-alias` semantics: scope-key alias only, or also a name-level
  alias for renamed flows? Defer to story level with real data.
* Use-case granularity: one product family = one UseCase in v1; revisit
  sub-clustering when the specialists land.
* Markdown emitter: confirmed v1 (its own story), not v2.

## References

* Brainstorming: `.primer/brainstorming/2026-06-29-nexus-assess-migration.md`
* ADR-025: replatform cross-instance analysis
* ADR-003: 3-gate assessment model
* PRD-002: assessment (records the cross-instance fence this lifts)
* Roadmap: `.primer/roadmap.md` -- 2026.07 Replatform Checklist
