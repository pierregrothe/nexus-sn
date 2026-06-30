# Story 01: replatform models

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a NEXUS developer building the replatform analysis layer,
I want frozen Pydantic models for use cases, workflows, and the migration
checklist,
so that the classifier, diff, and reporter share one typed data contract.

## Acceptance Criteria

AC1 (WorkflowRef):
**Given** `WorkflowRef` in `src/nexus/replatform/models.py`
**When** loaded
**Then** it is `frozen=True, strict=True, extra="forbid"` with fields
`key: str`, `name: str`, `type: str`, `scope: str`.

AC2 (UseCase):
**Given** `UseCase`
**When** loaded
**Then** frozen+strict+extra=forbid with fields `key: str`, `name: str`,
`domain: str`, `workflows: tuple[WorkflowRef, ...]`,
`evidence: tuple[str, ...]`.

AC3 (UseCaseInventory):
**Given** `UseCaseInventory`
**When** loaded
**Then** frozen+strict+extra=forbid with `profile: str`,
`captured_at: UtcDatetime`, `coverage: tuple[str, ...]`,
`use_cases: tuple[UseCase, ...]`.

AC4 (enums):
**Given** `ChecklistStatus` and `ChecklistKind`
**When** loaded
**Then** both are `StrEnum`; `ChecklistStatus = TODO | DONE | PARTIAL | EXTRA`,
`ChecklistKind = USE_CASE | WORKFLOW`.

AC5 (ChecklistItem fields):
**Given** a `ChecklistItem`
**When** loaded
**Then** frozen+strict+extra=forbid with fields `key: str`, `name: str`,
`domain: str`, `use_case_key: str`, `kind: ChecklistKind`,
`status: ChecklistStatus`, `built_count: int | None = None`,
`total_count: int | None = None`, `evidence: tuple[str, ...] = ()`.
(`domain`/`use_case_key`/`status` are required by the Story 03 sort key
`(domain, use_case_key, kind, key)`; recon-confirmed against drift.py.)

AC5b (ChecklistItem count invariant):
**Given** a `ChecklistItem`
**When** constructed with `kind=WORKFLOW`
**Then** `built_count is None and total_count is None`; **and when**
constructed with `kind=USE_CASE` **then** both counts are non-negative
`int` with `built_count <= total_count`. A `@model_validator(mode="after")`
enforces this and returns `Self`; violations raise `ValidationError`.
(`built_count`/`total_count` are declared `int | None` with no `Field`
constraint; ge=0 and the `<=` relation are enforced in the validator body,
not the annotation -- recon CONCERN on nullable+Field interaction.)

AC6 (MigrationChecklist):
**Given** `MigrationChecklist`
**When** loaded
**Then** frozen+strict+extra=forbid with `source_profile: str`,
`target_profile: str`, `source_captured_at: UtcDatetime`,
`target_captured_at: UtcDatetime`, `coverage: tuple[str, ...]`,
`items: tuple[ChecklistItem, ...]`.

AC7 (exports + purity):
**Given** the module
**When** imported
**Then** `__all__` lists every public model/enum, no field uses
`dict[str, Any]`, and the module imports nothing from `cli/` or `agents/`.

## Must NOT

- Must NOT add any classification, diff, or evaluation logic -- models only
  (that is Stories 02/03).
- Must NOT use `dict[str, Any]` in any field.
- Must NOT import from `src/nexus/cli/` or `src/nexus/agents/`.
- Must NOT modify any `src/nexus/capture/` model.

## Tasks / Subtasks

- [ ] Create `src/nexus/replatform/__init__.py` with lazy/explicit exports (AC7)
- [ ] Create `src/nexus/replatform/models.py` -- WorkflowRef, UseCase,
      UseCaseInventory, ChecklistItem, MigrationChecklist (AC1-3, AC6)
- [ ] Add `ChecklistStatus`, `ChecklistKind` StrEnums (AC4)
- [ ] Add `@model_validator(mode="after")` count invariant on ChecklistItem (AC5)
- [ ] Create `tests/fakes/replatform.py` -- canned inventories + checklist items
- [ ] Create `tests/test_replatform_models.py` (AC1-AC7)

## Existing Code

- `src/nexus/config/types.py` -- reuse `UtcDatetime` for timestamps.
- `src/nexus/plugins/models.py` -- reference for frozen tuple-field style.

## Dev Notes

### Modules Affected

- `src/nexus/replatform/__init__.py`, `src/nexus/replatform/models.py`
- `tests/fakes/replatform.py`, `tests/test_replatform_models.py`

### Testing Approach

- Construct each model from the Pydantic constructor; assert frozen by
  attempting mutation and expecting `ValidationError`.
- Cover the ChecklistItem count invariant: valid use_case, valid workflow,
  and both invalid cases (counts on workflow; built > total).
- No mocks; fakes provide reusable instances for Stories 02-06.

### Conventions

- Frozen+strict+extra=forbid (ADR-021); `UtcDatetime` from config.types.
- `StrEnum` from stdlib (Python 3.11+); file header + Google docstrings + `__all__`.

## References

- PRD: `.primer/prd/PRD-004-nexus-replatform-checklist.md#In Scope`
- Brainstorming: `.primer/brainstorming/2026-06-29-nexus-assess-migration.md#Recommendation 2`
- ADR: `.primer/adr/ADR-021-frozen-model-validators.md`
- ADR: `.primer/adr/ADR-025-replatform-cross-instance-analysis.md`
- Patterns: `.primer/patterns.md#pydantic-conventions`
