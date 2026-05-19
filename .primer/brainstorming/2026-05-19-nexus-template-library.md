# Brainstorming: NEXUS Template Library -- ApplyEngine + Skill/Workflow schemas + 3 community templates

Date: 2026-05-19
Mode: assumptions
Techniques: assumptions-mode (researcher brief -> 5 Unclear-item confirmations -> 2x adversarial passes)

## Context Brief

Project: NEXUS Python 3.14 ServiceNow architect CLI. Next planned
phase: 2026.06 Template Library (NowAssistSkill + Workflow schemas
+ first 3+ community templates + ApplyEngine).

What exists today (Confident, verified):

* Sync v1 shipped (`2026.05-setup-sync`):
  - `src/nexus/templates/models.py` -- `TemplateEntry(id, version, type, path)`,
    `TemplateManifest`, `CachedManifest`, `SyncSource` (frozen+strict+extra=forbid).
  - `src/nexus/templates/sync.py` -- `GitHubSync` + `GitHubTemplateClient`.
  - `src/nexus/templates/registry.py` -- `TemplateRegistry`.
  - `templates/manifest.json` is empty registry stub.
* Schema stubs in `src/nexus/templates/schemas/*.py` -- `now_assist_skill.py`,
  `workflow.py`, `ai_agent.py`, `catalog_item.py`, `recipe.py`, `project.py`
  -- all 1-line stubs. `apply.py` is a 1-line stub too.
* Assessment epic shipped (commits `5bb9081..b733de2`, 7 stories). Provides
  `GateContext`, `GateReport(verdict: PASS|BLOCK|ERROR)`, `Gate1Readiness`,
  `Gate2Validation`, `HealthScan`, `nexus assess` CLI with injected
  collaborators. `apply_result_loader` and `capture_runner` callables
  in `cli/commands_assess.py` stubbed at `NotImplementedError` --
  this epic wires them.
* Capture + write infrastructure:
  - `src/nexus/capture/update_set.py:UpdateSetWriter.push` --
    bundles `ConfigRecord` tuples into `sys_update_set` via
    `sys_update_xml` INSERT_OR_UPDATE.
  - `src/nexus/connectors/servicenow/protocol.py:ServiceNowClientProtocol.create_record(table, data)`.
  - `src/nexus/capture/tables.py:AI_AUTOMATION` group -- includes
    `ai_skill`, `sys_hub_flow`, `sys_hub_flow_input`, `sys_hub_flow_logic`,
    `sys_ai_agent`.
* CLI `nexus apply <template>` stub at `commands_top.py:152` raises
  `NotImplementedError`. `--dry-run` flag accepted but ignored.
* `PluginExecutor` (`src/nexus/plugins/executor.py:68-100`) is the
  reference orchestration pattern for SN operations.

Confirmed assumptions (5 Unclear items resolved):

1. **v1 template types**: NowAssistSkill + Workflow only. Other 4
   schemas stay as 1-line stubs for future epics.
2. **Apply mechanism**: update-set bundling via `UpdateSetWriter`. No
   direct REST writes path in v1.
3. **Re-apply semantics**: INSERT_OR_UPDATE -- replaces existing target
   records. Documented risk: silently overwrites human edits.
4. **Parameter substitution**: Pydantic-native field validators
   resolving `{{ env.X }}` at parse time. No Jinja2.
5. **Provenance**: `sys_update_set.name = NEXUS-apply-<template>-<ts>`
   + structured description metadata. Redundant local apply log at
   `~/.nexus/jobs/<job_id>/apply.jsonl` for survival if the SN-side
   update set is deleted.

Hard constraints:

* Pydantic frozen+strict+extra=forbid (ADR-021, patterns.md)
* Python 3.14 syntax (PEP 758, PEP 695, match/case)
* No mocks (fakes only, `tests/fakes/`)
* File-size caps (ADR-023): src/ 800, tests/ 1400
* 100% line coverage, mypy strict, pyright strict, ruff 0
* Layer order: templates can import capture, connectors, knowledge,
  cache (NOT agents, assessment, cli)

## Key Insights

1. **This epic is composition, not greenfield.** Sync v1, capture
   layer, UpdateSetWriter, ServiceNowClientProtocol, AI_AUTOMATION
   table group, Assessment gates, and the `nexus apply` CLI stub
   all exist. ApplyEngine wires them.

2. **Data flow**: template YAML -> Pydantic Document -> render_to_records
   -> ConfigRecord tuple -> UpdateSetWriter.push -> sys_update_set.
   This is identical to capture's reverse flow, read in the opposite
   direction. Same primitives.

3. **Pydantic-native env substitution bounds the templating surface.**
   `field_validator(mode="before")` parses `{{ env.X }}` and resolves
   via os.environ. Missing env var -> ValueError with the literal
   var name in the message. No string interpolation outside env vars
   in v1.

4. **INSERT_OR_UPDATE + update-set bundling = idempotent in target
   state, not in audit trail.** Same template applied twice produces
   two update sets, but the second is a noop relative to the first
   in record content (because UpdateSetWriter sends INSERT_OR_UPDATE
   sys_update_xml records, which SN treats as upserts).

5. **Provenance is free with update-set bundling.** `sys_update_set.name`
   carries the marker; description carries structured JSON (template_id,
   template_version, nexus_version, git_sha, applied_at). Queryable in
   SN UI; survives even if NEXUS is uninstalled. Local apply.jsonl
   is redundancy for the case where SN-side update set is deleted.

6. **NowAssistSkill -> 1 ai_skill record. Workflow -> sys_hub_flow
   + N children** (sys_hub_flow_input, sys_hub_flow_logic). Multi-record
   output is handled in the renderer, NOT in the schema. Schema layer
   = "one YAML = one TemplateDocument (one kind)"; renderer layer =
   "one document = N ConfigRecords".

7. **The Assessment epic left a clean integration seam.** `nexus
   apply` calls `capture_live -> Gate 1 -> ApplyEngine -> recapture ->
   Gate 2`. The Assessment `apply_result_loader` + `capture_runner`
   stubs get real implementations here. Story 06 of the Assessment
   epic was deliberately structured so this epic could swap real
   values in without changing the dispatch logic.

## Recommendations (build sequence)

1. **NowAssistSkill schema** -- Pydantic frozen+strict+extra=forbid
   mapping to ai_skill table. Fields verified against SN docs (or
   live-instance discovery as fallback) during the story. Includes
   `kind: Literal["now_assist_skill"]`, `id`, `version`, `target_scope`,
   `name`, `description`, `instructions`, `active`, etc. env-var
   field validators on string fields that author may want to
   parameterize.

2. **Workflow schema** -- Pydantic frozen+strict+extra=forbid mapping
   to sys_hub_flow + children. Nested models for inputs (sys_hub_flow_input)
   and logic (sys_hub_flow_logic). Same env-var validator pattern.

3. **TemplateDocument discriminated union** -- root-level discriminator
   on `kind`. `TemplateDocument = NowAssistSkill | Workflow`. Pydantic
   `Field(discriminator="kind")`. Multi-record bundling happens in
   the renderer; the schema sees one document.

4. **render_to_records(doc, scope_sys_id) -> tuple[ConfigRecord, ...]**
   -- pure function. NowAssistSkill renders to 1 record. Workflow
   renders parent + children. Returns ConfigRecord tuple that
   UpdateSetWriter can directly consume.

5. **ApplyEngine** -- orchestration core. Composes:
   ```
   load_template_document(template_dir) -> TemplateDocument
   resolve_scope_sys_id(target_scope_slug, sn_client) -> str
   render_to_records(doc, scope_sys_id) -> tuple[ConfigRecord, ...]
   create_sys_update_set(sn_client, template_id, template_version) -> str
   UpdateSetWriter.push(records, update_set_sys_id)
   write local apply.jsonl
   return ApplyResult
   ```

6. **ApplyResult model** populated (replaces Assessment's empty placeholder):
   ```
   class ApplyResult(BaseModel):
       update_set_sys_id: str
       update_set_name: str
       template_id: str
       template_version: str
       target_scope_sys_id: str
       applied_records: tuple[AppliedRecord, ...]
       instance_id: str
       started_at: UtcDatetime
       completed_at: UtcDatetime

   class AppliedRecord(BaseModel):
       table: str
       name: str
       requested_sys_id: str | None  # if author-declared
       action: AppliedAction  # REQUESTED | FAILED
       error_message: str | None
   ```

   `AppliedAction.FAILED` iff `http_status >= 400 OR "error" key
   present in SN response body`. Otherwise REQUESTED. WARNED tier
   deferred.

7. **`nexus apply <template-id>` orchestrator** -- wires everything:
   ```
   capture_live(target_scope) -> CaptureResult  # pre
   Gate1Readiness.evaluate(ctx(pre, phase=PRE_APPLY))
   if verdict=BLOCK and not --force: exit 2
   if verdict=ERROR: exit 1  # --force does NOT skip ERROR
   ApplyEngine.apply(...) -> ApplyResult
   if --skip-gate2: report apply_result; exit 0
   capture_live(target_scope) -> CaptureResult  # post
   Gate2Validation.evaluate(ctx(post, apply_result, POST_APPLY))
   render report; map verdict -> exit code (PASS=0, BLOCK=2, ERROR=1)
   ```
   Uses `BatchProgressProtocol` from CLI UX epic for per-record progress.
   Wires Assessment's `apply_result_loader` + `capture_runner` stubs.

8. **3 example templates + 3 per-template readiness rulesets**:
   - `templates/nowassist-incident-triage/template.yaml` + `manifest.yaml`
   - `templates/nowassist-tier1-rephrase/template.yaml` + `manifest.yaml`
   - `templates/simple-approval-flow/template.yaml` + `manifest.yaml`
   - `templates/assessments/nowassist-incident-triage-readiness.yaml`
     (applies_to: ["nowassist-incident-triage"])
   - `templates/assessments/nowassist-tier1-rephrase-readiness.yaml`
   - `templates/assessments/simple-approval-flow-readiness.yaml`

9. **CI validator** -- `scripts/validate_template_documents.py` walks
   `templates/<id>/template.yaml` and validates through `TemplateDocument`.
   `.github/workflows/validate-templates.yml` gains a new step.

10. **Update `templates/manifest.json`** -- list the 3 new templates
    with `id`, `version`, `type`, `path`. Existing `GitHubSync`
    consumes unchanged.

## Trade-offs

| Option | Pro | Con | Position |
|---|---|---|---|
| Update-set bundling | Clean, tracked, reversible | Adds a sys_update_set per apply | **Pick** (confirmed) |
| Direct REST writes | Faster | No audit trail | Reject (confirmed) |
| INSERT_OR_UPDATE re-apply | Idempotent in target state | Silently overwrites human edits | **Pick** -- document the risk in CLI help |
| Pydantic env validators | Type-safe; minimal surface | Less general than Jinja2 | **Pick** (confirmed) |
| Update-set metadata for provenance | Free; queryable | Update sets sometimes deleted | **Pick** + redundant local apply.jsonl |
| TemplateDocument root-level discriminator | One schema entry; type-safe | `kind` field on every YAML | **Pick** -- matches Assessment's RuleScope pattern |
| Workflow as multi-record render | Models reality | Renderer is non-trivial | **Pick** |
| Mandatory target_scope with "global" default | Schema enforces presence | Sentinel value | **Pick** |
| --force skips BLOCK only | Safe -- ERROR still aborts | Less powerful | **Pick** |
| --force skips BLOCK and ERROR | Maximum flexibility | Can apply against unknown state | Reject |
| AppliedRecord = REQUESTED \| FAILED only | Simple; matches v1 reality | No "warning" tier | **Pick**; add WARNED later if needed |
| Per-record post-state verification | Catches SN-side rejections | Extra round-trip per record | Reject for v1 -- record intent only |

## Out of Scope (anti-creep fence)

* **Other 4 schemas** (ai_agent, catalog_item, recipe, project) --
  separate epic. Stubs stay.
* **Jinja2 / general string templating** -- only `{{ env.X }}` env-var
  resolution via Pydantic field validators.
* **Rollback engine** -- Gate 2 reports drift; rolling back the
  update set is a separate epic.
* **Multi-instance apply** -- one apply, one instance.
* **Multi-step orchestration** -- Planner/Dispatcher live in 2026.07.
* **Cross-template dependencies** -- templates apply independently.
* **Template marketplace beyond GitHub** -- existing GitHubSync is
  the marketplace.
* **Live progress streaming per record** -- reuse `BatchProgressProtocol`.
* **Variable substitution beyond env vars** -- no `{{ cli.X }}`,
  no `{{ secret.X }}`, no `{{ instance.X }}`.
* **Dry-run mode** -- `--dry-run` flag stays NotImplementedError in v1.
* **Per-record post-state verification** -- only request intent
  recorded in v1.
* **--force escape past Gate 1 ERROR** -- ERROR always aborts; only
  BLOCK can be `--force`d through. No `--ignore-capture-errors`
  flag in v1.
* **WARNED tier in AppliedRecord** -- v1 = REQUESTED | FAILED only.

## Open Questions (NEEDS CLARIFICATION)

1. **Update-set state after Gate 2 fails.** Leave in_progress vs
   mark complete vs roll back. Defer to epic decomposition.
2. **Template-id format.** `templates/<slug>/template.yaml` vs
   `templates/<slug>/<version>/template.yaml`. Sync v1's TemplateEntry
   has a `version` field; whether the path encodes version is the
   question. Defer to epic decomposition.

## Adversarial Review

Two passes:

**v1** found 4 BLOCKERs + 6 CONCERNs + scope confusion (the reviewer
thought Assessment was still backlog because sprint-status.yaml was
stale; Assessment is actually shipped at commits `5bb9081..b733de2`).
Real BLOCKERs:
* Discriminator vs multi-record Workflow -- resolved by separating
  schema layer (one document = one kind) from renderer layer (one
  document -> N records).
* scope_sys_id origin unresolved -- resolved with `target_scope: str`
  field on TemplateDocument + CLI `--scope X` override.
* Per-template readiness rulesets missing -- resolved by shipping
  3 per-template rulesets alongside the 3 example templates.

**v2** found 4 residual gaps:
* scope_sys_id slug -> sys_id resolution path -- resolved by
  ApplyEngine resolving slug via one-shot sys_scope query before
  rendering; "global" sentinel resolves to well-known global sys_id.
* --force + Gate 1 ERROR interaction -- resolved by narrowing
  --force to BLOCK only; ERROR always aborts exit 1.
* Mandatory target_scope conflicts with global templates -- resolved
  with `target_scope: str = "global"` default sentinel.
* AppliedRecord SN-side warning -- resolved with FAILED predicate:
  `http_status >= 400 OR "error" in response body`. WARNED tier
  deferred.

No remaining BLOCKERs. Story-level design ambiguities (concrete
ai_skill / sys_hub_flow field shapes; update-set post-Gate-2 state;
template-id path format) surface during epic decomposition.

## Research Findings Appendix

### Sync v1 contracts (Confident)
* `src/nexus/templates/models.py` ships `TemplateEntry(id, version,
  type, path)` and `TemplateManifest` frozen+strict+extra=forbid.
* `src/nexus/templates/registry.py` -- `TemplateRegistry` manages
  the local cache at `paths.templates_dir`.
* `templates/manifest.json` -- currently empty `templates: []`.
* Connects to: Rec 10 (manifest update).

### Capture / write infrastructure (Confident)
* `src/nexus/capture/update_set.py:UpdateSetWriter.push` -- bundles
  `ConfigRecord` tuples into `sys_update_set` via `sys_update_xml`
  INSERT_OR_UPDATE.
* `src/nexus/connectors/servicenow/protocol.py:ServiceNowClientProtocol.create_record(table, data)`
  -- async; used by UpdateSetWriter to create the parent update-set
  record itself.
* `src/nexus/capture/tables.py:AI_AUTOMATION` -- table group covers
  ai_skill, sys_hub_flow, sys_hub_flow_input, sys_hub_flow_logic,
  sys_ai_agent.
* Connects to: Recs 4 + 5 (ApplyEngine composition).

### Assessment integration (Confident)
* Assessment epic shipped 7 stories on main (`5bb9081..b733de2`).
* `src/nexus/assessment/context.py:ApplyResult` -- empty placeholder.
* `src/nexus/cli/commands_assess.py` -- `apply_result_loader` +
  `capture_runner` callables stubbed at NotImplementedError.
* Gate verdict mapping: PASS=0, BLOCK=2, ERROR=1 (Assessment Story 04 + 06).
* Connects to: Recs 6 + 7 (ApplyResult population + nexus apply
  wiring).

### CLI scaffolding (Confident)
* `src/nexus/cli/commands_top.py:152` -- `apply` stub raises
  NotImplementedError; `--dry-run` flag accepted but ignored.
* `src/nexus/cli/commands_assess.py` -- pattern of injected
  collaborators for testability. Recommend mirroring for
  `commands_apply.py`.
* Connects to: Rec 7 (nexus apply wiring) + Rec 8 (CLI structure).

### PluginExecutor reference (Likely)
* `src/nexus/plugins/executor.py:68-100` -- orchestration pattern
  with stateful tracking + OperationResult. ApplyEngine adapts
  this shape but does NOT need async progress polling (update-set
  apply is a single round-trip; SN doesn't return a long-running
  job for content writes).
* Connects to: Rec 5 (ApplyEngine design).

### ADRs governing this epic (Confident)
* ADR-002: Template GitHub sync (sync v1 already implements).
* ADR-003: 3-gate assessment model (Assessment epic shipped).
* ADR-023: 800-line src/ cap.

## Session Notes

### Round 1: Researcher brief
Returned in ~80 seconds. 5 Confident findings, 4 Likely findings,
5 Unclear items elevated to user.

### Round 2: User confirmation
All 5 Unclear items resolved:
* v1 = NowAssistSkill + Workflow only
* Update-set bundling
* INSERT_OR_UPDATE re-apply
* Pydantic env-var validators
* Update-set name+description provenance

### Round 3: Adversarial v1
Flagged 4 BLOCKERs (discriminator+multi-record, scope_sys_id origin,
per-template readiness rulesets, scope-confusion vs already-shipped
Assessment) + 6 CONCERNs. All addressable.

### Round 4: Adversarial v2
Confirmed v1 BLOCKERs closed. Found 4 residual gaps (slug resolution,
--force+ERROR interaction, target_scope-on-global templates,
AppliedRecord SN-warning semantics). All resolved in the v2 synthesis.
No remaining BLOCKERs at synthesis level.
