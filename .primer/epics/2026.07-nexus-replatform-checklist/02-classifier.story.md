# Story 02: deterministic use-case classifier

Status: backlog
Spec-Clarity: high
Depends-On: 01

## Story

As a NEXUS user inventorying an instance,
I want a deterministic function that turns captures into a use-case inventory,
so that I get a stable, LLM-free classification I can diff across instances.

## Acceptance Criteria

AC1 (signature + purity):
**Given** `classify(captures, scopes, plugin_inventory, catalog)` in
`src/nexus/replatform/classifier.py`
**When** called
**Then** it accepts `captures: tuple[CaptureResult, ...]`,
`scopes: ScopeManifest`, `plugin_inventory: PluginInventory`,
`catalog: ProductCatalog` and returns `UseCaseInventory`, performing no
I/O, no LLM call, and no MCP call (pure function).

AC2 (natural-key normalization):

| name input | type (table) | scope (ScopeEntry.scope) | key output |
|---|---|---|---|
| `Create Incident` | `sys_hub_flow` | `x_acme_app` | `x_acme_app\|sys_hub_flow\|create incident` |
| `  Create   Incident ` | `sys_hub_flow` | `x_acme_app` | `x_acme_app\|sys_hub_flow\|create incident` |
| `CREATE INCIDENT` | `sys_hub_flow` | `x_acme_app` | `x_acme_app\|sys_hub_flow\|create incident` |
| `Greeting` | `ai_skill` | `global` | `global\|ai_skill\|greeting` |

Normalization = `casefold()` + internal-whitespace collapse + strip.

AC3 (scope key resolution):
**Given** a `ConfigRecord` whose `scope_sys_id` resolves via `ScopeManifest`
to `ScopeEntry.scope`
**When** the key is built
**Then** the scope component is the technical `ScopeEntry.scope`, NOT
`scope_name` and NOT `scope_sys_id`. **And** when `scope_sys_id` is absent
from `scopes`, the record is bucketed under domain `Uncategorized` with the
scope component falling back to the normalized `scope_name`.

AC4 (WorkflowRef extraction):
**Given** a captured `ConfigRecord`
**When** classified
**Then** `WorkflowRef.name = fields["name"]`, `WorkflowRef.type =
record.table`, `WorkflowRef.scope = <technical scope key>`,
`WorkflowRef.key = <normalized key>`.

AC5 (product-family bucketing):
**Given** scopes present in the product catalog
**When** classified
**Then** their workflows group into a `UseCase` whose `domain` is the
catalog product family; **and** scopes absent from the catalog group under
`domain = "Uncategorized"`.

AC6 (coverage + evidence):
**Given** captures with `table_group` values
**When** classified
**Then** `UseCaseInventory.coverage` lists the distinct table groups, and
each `UseCase.evidence` lists the scopes (and any plugin ids) that justify it.

AC7 (empty + multi-scope):
**Given** an empty capture tuple
**Then** `classify` returns an inventory with zero use_cases; **and given**
records from multiple scopes mapping to the same family, they merge into one
`UseCase` with workflows from all contributing scopes.

## Must NOT

- Must NOT call the Anthropic API, any MCP tool, or the network.
- Must NOT read files or query ServiceNow -- inputs are already-loaded models.
- Must NOT use sys_id in any natural key.
- Must NOT modify `src/nexus/capture/` or `src/nexus/plugins/` models.

## Tasks / Subtasks

- [ ] Create `src/nexus/replatform/classifier.py` -- `classify(...)` (AC1, AC5-7)
- [ ] Add `_normalize_key(name, type, scope)` helper (AC2)
- [ ] Add scope-resolution helper over `ScopeManifest` with Uncategorized
      fallback (AC3)
- [ ] Add `WorkflowRef` extraction from `ConfigRecord.fields` (AC4)
- [ ] Extend `tests/fakes/replatform.py` with `FakeScopeManifest` + capture
      records carrying a `name` field
- [ ] Create `tests/test_replatform_classifier.py` (AC1-AC7)
- [ ] Update `src/nexus/replatform/__init__.py` exports

## Existing Code

- `src/nexus/capture/models.py` -- `CaptureResult`, `ConfigRecord`
  (`fields`, `table`, `scope_sys_id`), `ScopeManifest`, `ScopeEntry.scope`.
- `src/nexus/capture/tables.py` -- `AI_AUTOMATION` group / `table_group` keys.
- `src/nexus/plugins/models.py` -- `PluginInventory`, `PluginInfo.product_family`.
- Product catalog loader (from PR #54) -- scope -> family mapping.

## Dev Notes

### Modules Affected

- `src/nexus/replatform/classifier.py`, `src/nexus/replatform/__init__.py`
- `tests/fakes/replatform.py`, `tests/test_replatform_classifier.py`

### Testing Approach

- Build `CaptureResult` + `ScopeManifest` fakes; assert produced inventory
  equals an expected frozen `UseCaseInventory` (byte-stable, like grouped ERD).
- Table-driven test for `_normalize_key` per AC2.
- Cover Uncategorized fallback (custom scope, missing scope sys_id) and the
  multi-scope merge.

### Conventions

- Pure function, no I/O (mirrors `plugins/diff.py` style).
- Python 3.14 `match/case` with `case _:` if dispatching on table type.
- File header + Google docstrings + `__all__`.

## References

- PRD: `.primer/prd/PRD-004-nexus-replatform-checklist.md#In Scope`
- Brainstorming: `.primer/brainstorming/2026-06-29-nexus-assess-migration.md#Recommendation 3`
- ADR: `.primer/adr/ADR-025-replatform-cross-instance-analysis.md#Decision 2`
- Patterns: `.primer/patterns.md#layer-order`
