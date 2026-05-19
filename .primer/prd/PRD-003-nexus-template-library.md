---
id: PRD-003
title: NEXUS Template Library -- ApplyEngine + Skill/Workflow schemas
status: draft
date: 2026-05-19
adrs: [ADR-002, ADR-003]
charter_link: charter.md
milestone: 2026.06-template-library
---

# PRD-003: NEXUS Template Library -- ApplyEngine + Skill/Workflow schemas

## Problem

NEXUS can sync templates from GitHub (sync v1, shipped 2026.05),
assess instance state with gates (Assessment epic, shipped 2026.06),
and capture configuration to YAML archives. What it cannot do: take
a community template YAML and deploy it to a target ServiceNow
instance. The `nexus apply <template>` command exists as a stub
raising `NotImplementedError`; the `apply_result_loader` and
`capture_runner` callables in the Assessment CLI dispatcher are
both stubbed. This PRD ships the closing piece -- declarative
templates, an ApplyEngine that writes them via update sets, and
`nexus apply` orchestration that wraps Gate 1 + ApplyEngine +
Gate 2.

## Users

* Operators deploying community templates ("install incident-triage
  NowAssist skill") via `nexus apply <template>`.
* Template authors contributing YAML to the GitHub registry.
* CI pipelines wrapping `nexus apply` to deploy reference templates
  to dev instances on every push.
* Operators auditing what NEXUS applied (queryable via
  sys_update_set name+description metadata).

## In Scope (must-haves)

* **NowAssistSkill Pydantic schema** mapping to ai_skill table.
  Frozen+strict+extra=forbid. `kind: Literal["now_assist_skill"]`
  discriminator. Includes `id`, `version`, `target_scope`, `name`,
  `description`, `instructions`, `active`, etc. Field shape verified
  against ServiceNow ai_skill documentation (or live-instance
  discovery fallback).
* **Workflow Pydantic schema** mapping to sys_hub_flow + child
  rows (sys_hub_flow_input, sys_hub_flow_logic). Same frozen
  pattern. Nested models for children.
* **`{{ env.X }}` field-validator** -- Pydantic `@field_validator(mode="before")`
  resolves `{{ env.SN_INSTANCE_URL }}` syntax to `os.environ["SN_INSTANCE_URL"]`
  at parse time. Missing env var raises `ValueError` with the literal
  variable name. No Jinja2, no general string templating.
* **TemplateDocument discriminated union** -- `NowAssistSkill | Workflow`
  with `kind` as the discriminator. One YAML file = one
  TemplateDocument.
* **`render_to_records(document, scope_sys_id) -> tuple[ConfigRecord, ...]`**
  pure function. NowAssistSkill -> 1 record. Workflow -> parent +
  N children.
* **ApplyEngine** -- composes load -> resolve_scope -> render ->
  create sys_update_set -> UpdateSetWriter.push -> ApplyResult.
  Resolves `target_scope` slug to sys_id via one-shot sys_scope
  query. "global" sentinel resolves to the well-known global sys_id.
* **ApplyResult model** (replaces Assessment's empty placeholder):
  ```
  update_set_sys_id: str
  update_set_name: str
  template_id: str
  template_version: str
  target_scope_sys_id: str
  applied_records: tuple[AppliedRecord, ...]
  instance_id: str
  started_at: UtcDatetime
  completed_at: UtcDatetime
  ```
  AppliedRecord(table, name, requested_sys_id|None, action, error_message|None).
  AppliedAction = REQUESTED | FAILED. FAILED iff `http_status >= 400 OR
  "error" in response body`.
* **Provenance metadata** -- `sys_update_set.name = NEXUS-apply-<template>-<ts>`
  + description carrying structured JSON `{nexus: {template_id, template_version,
  nexus_version, git_sha, applied_at}}`. Redundant local apply log at
  `~/.nexus/jobs/<job_id>/apply.jsonl`.
* **`nexus apply <template-id>` CLI orchestrator** wiring:
  ```
  capture_live(target_scope) -> CaptureResult  # pre
  Gate1Readiness.evaluate(ctx(pre, PRE_APPLY))
  if verdict=BLOCK and not --force: exit 2
  if verdict=ERROR: exit 1  # --force does NOT skip ERROR
  ApplyEngine.apply(...) -> ApplyResult
  if --skip-gate2: render apply_result; exit 0
  capture_live(target_scope) -> CaptureResult  # post
  Gate2Validation.evaluate(ctx(post, apply_result, POST_APPLY))
  render report; map verdict -> exit code (PASS=0, BLOCK=2, ERROR=1)
  ```
  Uses `BatchProgressProtocol` (CLI UX epic) for per-record progress.
  Wires Assessment's `apply_result_loader` + `capture_runner` stubs.
* **3 example templates + 3 per-template readiness rulesets**:
  - `templates/nowassist-incident-triage/template.yaml`
  - `templates/nowassist-tier1-rephrase/template.yaml`
  - `templates/simple-approval-flow/template.yaml`
  - Each ships with a sibling `manifest.yaml` (TemplateEntry shape)
    and a `templates/assessments/<id>-readiness.yaml` ruleset with
    `applies_to: [<id>]`.
* **CI template-document validator** -- `scripts/validate_template_documents.py`
  walks `templates/*/template.yaml` and parses through TemplateDocument.
  Extends `.github/workflows/validate-templates.yml`.
* **Sync v1 manifest refresh** -- `templates/manifest.json` lists the
  3 new templates. Existing `GitHubSync` consumes unchanged.
* **Fakes in `tests/fakes/`** -- `FakeServiceNowClient` (already exists;
  extend if needed), `FakeUpdateSetWriter`, `FakeTemplateDocument`
  builders. No mocks.

## Out of Scope (anti-creep fence -- the load-bearing section)

* **Other 4 schemas** (ai_agent, catalog_item, recipe, project) --
  separate epic. Stubs stay 1-line.
* **Jinja2 / general string templating** -- only `{{ env.X }}`
  resolution via Pydantic field validators in v1.
* **Rollback engine** -- Gate 2 reports drift; rolling back the
  update set is a separate epic (Agent Specialists or dedicated
  rollback epic). `--rollback` flag and rollback CLI are out.
* **Multi-instance apply** -- one apply, one instance. Multi-instance
  fan-out is a higher-level loop later.
* **Multi-step orchestration / Planner / Dispatcher** -- 2026.07
  Agent Specialists epic.
* **Cross-template dependencies** -- templates apply independently.
  "Template A requires B applied first" is rejected for v1.
* **Template marketplace beyond GitHub** -- existing GitHubSync
  registry is the marketplace.
* **Live progress streaming per record** -- reuse `BatchProgressProtocol`
  from CLI UX epic; no new UI primitives.
* **Variable substitution beyond env vars** -- no `{{ cli.X }}`,
  no `{{ secret.X }}`, no `{{ instance.X }}` in v1.
* **Dry-run mode** -- `nexus apply --dry-run` flag stays
  NotImplementedError in v1. Most likely scope-creep request;
  rejected here.
* **Per-record post-state verification** -- ApplyResult records
  intent (what was requested), not live post-state. Verification
  is Gate 2's job.
* **--force escape past Gate 1 ERROR** -- ERROR always aborts;
  only BLOCK can be forced through. No `--ignore-capture-errors`
  flag in v1.
* **WARNED tier in AppliedRecord** -- v1 = REQUESTED | FAILED only.
* **Update-set rollback or merge** -- update sets land in
  in_progress state. Whether to auto-mark complete or leave for
  manual review is deferred.
* **Direct REST writes (bypass update set)** -- update-set bundling
  is the only path in v1.

## Acceptance Criteria

- [ ] `NowAssistSkill` and `Workflow` Pydantic models in
  `src/nexus/templates/schemas/`. Frozen+strict+extra=forbid;
  pyright + mypy strict 0 errors; field shape documented with
  citation to SN docs or live-instance source.
- [ ] `TemplateDocument` discriminated union accepts both variants;
  YAML round-trips through Pydantic without loss.
- [ ] `{{ env.X }}` substitution: parsing succeeds with var set;
  parsing fails with clear "env var X is not set" when unset.
- [ ] `render_to_records(doc, scope_sys_id)` returns the expected
  ConfigRecord tuple for each variant; NowAssistSkill -> 1 record,
  Workflow -> parent + N children.
- [ ] ApplyEngine end-to-end: load + render + create update set +
  push records + emit ApplyResult; smoke test against
  FakeServiceNowClient succeeds.
- [ ] `nexus apply <id>` wires Gate 1 + ApplyEngine + Gate 2 with
  verdict-to-exit mapping. BLOCK + no --force -> exit 2; ERROR ->
  exit 1; PASS -> exit 0.
- [ ] `--force` skips Gate 1 BLOCK verdict only (ERROR still aborts).
- [ ] `--skip-gate2` runs Gate 1 + ApplyEngine then exits without
  recapture or Gate 2.
- [ ] 3 example templates ship under `templates/<id>/` with
  per-template readiness rulesets under `templates/assessments/`.
- [ ] CI validator runs on every PR touching `templates/**`.
- [ ] All new modules under ADR-023 size caps (likely 6-9 modules
  for ApplyEngine + schemas + renderer + CLI).
- [ ] Sprint-status updated; all stories at `done`.

## Success Metrics

* `nexus apply nowassist-incident-triage` end-to-end against a dev
  ServiceNow instance creates the ai_skill record and the
  sys_update_set with NEXUS provenance metadata.
* Re-running `nexus apply` against the same template is a noop in
  target state (sys_update_xml INSERT_OR_UPDATE).
* Gate 1 catches "target scope does not exist" before any write.
* Gate 2 catches "ai_skill record missing after apply" if the apply
  silently failed.
* Time-to-first-template for a contributor: <2 hours from reading
  the YAML example to opening a PR.

## Dependencies

* **Sync v1** (shipped 2026.05): `TemplateEntry`, `TemplateManifest`,
  `GitHubSync`, `TemplateRegistry`.
* **Capture layer** (shipped): `CaptureResult`, `ConfigRecord`,
  `UpdateSetWriter`, `AI_AUTOMATION` table group.
* **Connectors layer** (shipped): `ServiceNowClientProtocol.create_record`.
* **Assessment epic** (shipped 2026.06): `GateContext`, `GateReport`,
  `Gate1Readiness`, `Gate2Validation`, `commands_assess.py`
  `apply_result_loader` + `capture_runner` stubs to wire.
* **CLI UX epic** (shipped 2026.05): `BatchProgressProtocol` for
  per-record progress.
* **ADRs**: ADR-002 (GitHub sync), ADR-003 (3-gate model),
  ADR-021 (frozen models), ADR-022 (CLI deferred imports),
  ADR-023 (file-size caps).

## Out of Library Scope (always)

Template Library ships as part of the NEXUS CLI. All code lives
under `src/nexus/templates/` (plus CLI wiring in `src/nexus/cli/`).
Runtime concerns owned by other layers:

* ServiceNow REST transport -- connectors layer.
* OAuth credential refresh -- auth layer.
* Console rendering primitives -- ui/components.
* Capture / archive serialization -- capture layer.
* Assessment / gates -- assessment layer.

Template Library depends on but does not duplicate any of the above.

## Open Questions

* Update-set state after Gate 2 fails: leave in_progress vs mark
  complete vs auto-rollback. Defer to epic decomposition.
* Template-id path encoding: `templates/<slug>/template.yaml` vs
  `templates/<slug>/<version>/template.yaml`. Defer.
* Concrete ai_skill / sys_hub_flow field shape verification: each
  schema story includes a "verify against source" task before
  finalizing.

## References

* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-template-library.md`
* ADR-002: Template GitHub sync
* ADR-003: 3-gate assessment model (consumer)
* ADR-021: Frozen model validators
* ADR-023: File size limits
* Roadmap: `.primer/roadmap.md` -- 2026.06 Template Library phase
* PRD-002: NEXUS Assessment (sibling, shipped)
* Existing scaffolding: `src/nexus/templates/schemas/*.py` (1-line stubs)
* Existing CLI stub: `src/nexus/cli/commands_top.py:152`
