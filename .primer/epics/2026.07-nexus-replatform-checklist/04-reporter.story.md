# Story 04: replatform reporter (console + markdown + coverage Notice)

Status: done
Spec-Clarity: high
Depends-On: 01

## Story

As a user reading a migration checklist,
I want it rendered to the console and optionally to a markdown file, with a
loud warning when coverage is thin,
so that I can act on it and never mistake an empty checklist for "done".

## Acceptance Criteria

AC1 (console render via existing components):
**Given** a `MigrationChecklist`
**When** `render_checklist(checklist, render_context)` is called
**Then** it renders using ONLY existing `ui/components/` (`DataTable`,
`KeyValuePanel`, `StatusBadge`, `Notice`) -- no new UI primitive is created.

AC2 (status grouping):
**Given** a checklist with mixed statuses
**When** rendered
**Then** items are grouped by `domain` and each row shows status as a
`StatusBadge` (TODO / DONE / PARTIAL / EXTRA), with use-case rows showing the
`built_count/total_count` fraction.

AC3 (markdown emitter):
**Given** `--out checklist.md`
**When** `write_markdown(checklist, path)` is called
**Then** it writes a UTF-8 markdown file with a per-domain section and GitHub
task-list checkboxes (`- [x]` for DONE, `- [x]` for TODO/PARTIAL), and the
PARTIAL fraction inline. Re-running with identical input produces identical
bytes.

AC4 (empty/thin-coverage Notice):
**Given** a checklist whose source inventory contributed zero items
**When** rendered (console) or written (markdown)
**Then** a prominent `Notice.warn(...)` is emitted stating the source
inventory is empty and that capture only covers custom AI/automation scopes
today -- "a clean checklist is not proof nothing needs migrating".

AC5 (summary panel):
**Given** any checklist
**When** rendered
**Then** a `KeyValuePanel` summarizes counts: total use cases, DONE / PARTIAL
/ TODO use cases, and EXTRA count.

## Must NOT

- Must NOT create a new UI primitive or use `FramedViewer`.
- Must NOT mutate the checklist.
- Must NOT compute status -- consume Story 03 output as-is.
- Must NOT use unicode/emoji in any rendered or written output (ASCII only).

## Tasks / Subtasks

- [x] Create `src/nexus/replatform/reporter.py` -- `render_checklist(...)` (AC1, AC2, AC5)
- [x] Add `write_markdown(checklist, path)` emitter (AC3)
- [x] Add empty/thin-coverage Notice logic (AC4)
- [x] Create `tests/test_replatform_reporter.py` (AC1-AC5)
- [x] Update `src/nexus/replatform/__init__.py` exports

## Existing Code

- `src/nexus/ui/components/` -- `DataTable`, `KeyValuePanel`, `StatusBadge`, `Notice`.
- `src/nexus/assessment/reporter.py` -- pattern for rendering a report via
  components; mirror its structure.
- `src/nexus/cli/commands_plugins_advisories.py` -- rendering reference.

## Dev Notes

### Modules Affected

- `src/nexus/replatform/reporter.py`, `src/nexus/replatform/__init__.py`
- `tests/test_replatform_reporter.py`

### Testing Approach

- Render into a captured `RenderContext` console; assert rows/badges present.
- Markdown: write to `tmp_path`; assert byte-stable round-trip and checkbox
  mapping; assert the Notice appears on a zero-item source.

### Conventions

- Reuse components only (ADR-style "no new UI surface" from PRD-002 precedent).
- ASCII only; file header + Google docstrings + `__all__`.

## References

- PRD: `.primer/prd/PRD-004-nexus-replatform-checklist.md#In Scope`
- Brainstorming: `.primer/brainstorming/2026-06-29-nexus-assess-migration.md#Recommendation 6`
- Existing: `src/nexus/assessment/reporter.py`, `src/nexus/ui/components/`
