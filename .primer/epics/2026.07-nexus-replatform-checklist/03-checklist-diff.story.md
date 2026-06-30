# Story 03: bi-directional checklist diff

Status: backlog
Spec-Clarity: high
Depends-On: 01

## Story

As a team replatforming onto a clean instance,
I want a diff that compares two use-case inventories and emits a status per
item,
so that I see what is still TODO and watch it tick to DONE across re-runs.

## Acceptance Criteria

AC1 (signature + purity):
`build_checklist(source: UseCaseInventory, target: UseCaseInventory,
aliases: tuple[tuple[str, str], ...] = ()) -> MigrationChecklist` in
`src/nexus/replatform/diff.py` is a pure function (no I/O), the analog of
`plugins/drift.compute_drift`.

AC2 (workflow-grain status):

| WorkflowRef key in source | in target | ChecklistItem.status |
|---|---|---|
| present | absent | TODO |
| present | present | DONE |
| absent | present | EXTRA |

Matching is on the normalized `WorkflowRef.key` only -- never sys_id.

AC3 (use-case rollup):

| workflows in a use case | use-case status | built_count/total_count |
|---|---|---|
| all DONE | DONE | total/total |
| none DONE (all TODO) | TODO | 0/total |
| some DONE | PARTIAL | built/total |

`total_count` counts source workflows; `built_count` counts those also in target.

AC4 (scope-alias remap):
**Given** `aliases = (("x_oldcorp_app", "x_newcorp_app"),)`
**When** the diff runs
**Then** target keys whose scope component is `x_newcorp_app` are remapped to
`x_oldcorp_app` BEFORE matching, so a renamed-scope workflow reads DONE rather
than TODO+EXTRA.

AC5 (stable ordering):
**Given** any inputs
**When** the checklist is built
**Then** `items` are sorted by `(domain, use_case_key, kind, key)` ascending,
byte-stable across runs.

AC6 (EXTRA is informational):
**Given** a target use case absent from source
**When** diffed
**Then** its workflows appear as `EXTRA` items and it does NOT inflate any
source use-case `total_count`.

AC7 (metadata):
**Given** source and target inventories
**Then** the `MigrationChecklist` carries both profiles, both `captured_at`
timestamps, and the union of both `coverage` tuples.

## Must NOT

- Must NOT match on sys_id.
- Must NOT mutate either input inventory.
- Must NOT perform I/O, network, or MCP calls.
- Must NOT render output -- that is Story 04.

## Tasks / Subtasks

- [ ] Create `src/nexus/replatform/diff.py` -- `build_checklist(...)` (AC1)
- [ ] Implement workflow-grain status (AC2) and use-case rollup (AC3)
- [ ] Implement `_apply_aliases(target, aliases)` remap (AC4)
- [ ] Implement stable sort (AC5) and EXTRA handling (AC6)
- [ ] Create `tests/test_replatform_diff.py` (AC1-AC7) using Story 01 fakes
- [ ] Update `src/nexus/replatform/__init__.py` exports

## Existing Code

- `src/nexus/plugins/drift.py` -- `compute_drift` set-diff + stable-sort
  pattern to mirror.
- `src/nexus/replatform/models.py` (Story 01) -- output models.

## Dev Notes

### Modules Affected

- `src/nexus/replatform/diff.py`, `src/nexus/replatform/__init__.py`
- `tests/test_replatform_diff.py`

### Testing Approach

- Build paired `UseCaseInventory` fakes; assert the produced
  `MigrationChecklist` equals an expected frozen instance.
- One test per AC2/AC3 row; one alias-remap test (AC4); one ordering test (AC5).
- Cross-instance equality test: same logical workflow, different sys_ids,
  same key -> DONE.

### Conventions

- Pure function over loaded models; dict-keyed set diff like `drift.py`.
- Python 3.14 syntax; file header + Google docstrings + `__all__`.

## References

- PRD: `.primer/prd/PRD-004-nexus-replatform-checklist.md#In Scope`
- Brainstorming: `.primer/brainstorming/2026-06-29-nexus-assess-migration.md#Recommendation 5`
- ADR: `.primer/adr/ADR-025-replatform-cross-instance-analysis.md#Decision 2`
- Existing: `src/nexus/plugins/drift.py`
