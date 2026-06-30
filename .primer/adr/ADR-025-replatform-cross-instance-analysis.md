# ADR-025: Replatform analysis layer + cross-instance natural-key matching

**Status:** accepted
**Date:** 2026-06-29
**Enforcement:** agent
**prd:** PRD-004

## Context

The shipped assessment layer (ADR-003) is a single-instance, declarative
rule-engine gate validator; PRD-002 explicitly fences out "cross-instance
comparison -- one capture, one assessment." A new customer need -- replatforming
onto a fresh "clean" instance after an acquisition -- requires comparing TWO
instances and emitting a per-domain build checklist (the use cases and workflows
on the old instance, auto-ticked as each is built on the new one). This crosses
the ADR-003 / PRD-002 single-instance fence and forces three architectural
decisions: where the code lives, how cross-instance identity works, and how the
CLI is shaped. See `.primer/brainstorming/2026-06-29-nexus-assess-migration.md`.

## Decision

1. **Separate package.** Replatform analysis lives in a NEW
   `src/nexus/replatform/` package, NOT inside `src/nexus/assessment/` (the
   rule-engine). It consumes `CaptureResult` + `ScopeManifest` + `PluginInventory`
   and must not import or couple to the RuleEngine.
2. **Natural-key identity, never sys_id.** Cross-instance matching uses a
   normalized natural key `(technical_scope_key, type, casefold(name))`. A fresh
   instance reassigns every sys_id, so sys_id is unusable. The technical scope key
   comes from `ScopeEntry.scope` via `ScopeManifest` -- not the localizable
   `ConfigRecord.scope_name`, nor `scope_sys_id` (instance-specific).
3. **Advisory only.** The layer reports a checklist and NEVER mutates either
   instance, consistent with ADR-003 ("assessment only reports") and the charter's
   Hard Product Limits. No `--apply`; building is `nexus capture push` + ApplyEngine.
4. **CLI under `assess`.** `assess` becomes a Typer command group; the bare
   gate/health behavior is preserved behind an `invoke_without_command` +
   `ctx.invoked_subcommand` guard; new subcommands `inventory` and `migration`
   are added. `commands_top.py` is a build target.
5. **No MCP in the analysis layer.** `classify` and `build_checklist` consume
   captured data only, mirroring PRD-002's "rules consume CaptureResult only."

## Consequences

- PRD-002's cross-instance fence is consciously lifted for the `assess migration`
  subcommand ONLY; the gate semantics (bare `assess` / `--for` / `--job`) are
  unchanged. PRD-004 records the amendment.
- v1 classification is deterministic (product-family bucketing); AI enrichment
  depends on the 2026.07 Agent Specialists and is v2.
- Fidelity is bounded by capture coverage (the `AI_AUTOMATION` table group today);
  the reporter MUST flag empty/thin coverage so a clean checklist is never misread
  as "nothing to migrate."
- The leaf-to-group conversion of `assess` changes its `--help` / completion tree
  while preserving runtime gate behavior.
