# Story 03: `nexus migrate select`

Status: done
Spec-Clarity: high
Depends-On: 02

## Recon decision (2026-07-02)

`select` consumes a JSON-dumped `MigrationChecklist` via `--from-checklist`
(the same shape `nexus assess migration --out checklist.json` already
produces) rather than re-running the live diff in-process. This keeps
`migrate/` decoupled from live instance access per the ADR-026#Decision 1
layer boundary (`migrate/` consumes `MigrationChecklist`, it does not
recompute it), and avoids duplicating `commands_assess_replatform.py`'s
live-capture wiring inside `commands_migrate.py`.

## Story

As a Solution Consultant curating a selective migration,
I want `nexus migrate select` to seed a Selection YAML from an existing
replatform checklist,
so that every checklist item appears exactly once with an initial
disposition I can then curate and commit under git PR review.

## Acceptance Criteria

AC1 (seed completeness):
**Given** a `MigrationChecklist` JSON file with N items
**When** `nexus migrate select --from-checklist checklist.json --out
selection.yaml` runs
**Then** the emitted `Selection` contains exactly N `SelectionItem`
entries, one per checklist item key, each carrying `disposition=
"undecided"` and empty `annotation`/`annotated_by`.

AC2 (exactly-once invariant):
**Given** a checklist whose items may share keys across kind boundaries
**When** `select` seeds the Selection
**Then** each distinct checklist item key appears in the output exactly
once (no duplicates, no omissions) -- verified by set-equality between
checklist item keys and selection item keys.

AC3 (no status-based auto-inclusion):
**Given** a checklist item with `status=DONE` or `status=EXTRA`
**When** seeded
**Then** its default disposition is still `"undecided"` -- v1 seeds
everything undecided; curation is a later, human, git-reviewed step
(ADR-026#Decision 2).

AC4 (exit codes, GWT):
**Given** `--from-checklist` points to a missing or malformed file
**When** `select` runs
**Then** it prints an error to stderr and exits 1; on success it exits 0.

AC5 (byte-stable emitter reuse):
**Given** a successful `select` run
**When** `--out` is written
**Then** it is produced via the Story 02 `emit_plan_yaml` byte-stable YAML
emit path, not an ad hoc `yaml.dump` call in the CLI module.

## Must NOT

- Must NOT mutate either ServiceNow instance -- no live calls at all in
  this command; it reads a checklist file already produced by `nexus assess
  migration`.
- Must NOT touch `src/nexus/cli/commands_assess.py` or the `assess` group
  -- `migrate` is a new, separate Typer group.
- Must NOT auto-populate `disposition` beyond `"undecided"` -- curation is
  a human, git-reviewed step (ADR-026#Decision 2).

## Tasks / Subtasks

- [x] Create `src/nexus/cli/commands_migrate.py` -- new `migrate_app` Typer
      group (AC1)
- [x] Register `migrate_app` in `src/nexus/cli/apps.py`
      (`app.add_typer(migrate_app)`) (AC1)
- [x] Implement `run_select(*, checklist_path, out, render_context) -> int`
      (thin-wrapper pattern per Story 06 of the 2026.07 epic) (AC1-AC4)
- [x] Implement checklist-to-Selection seeding: one `SelectionItem` per
      `ChecklistItem.key` (AC1-AC3)
- [x] Wire `@migrate_app.command("select")` Typer command over `run_select`
      (AC4)
- [x] Create `tests/cli/test_migrate_select_cmd.py` using `CliRunner` +
      `tests/fakes/migrate.py` / `tests/fakes/replatform.py` fixtures
      (AC1-AC5)

## Existing Code

- `src/nexus/cli/commands_assess_replatform.py` -- the thin-Typer-wrapper +
  injectable-collaborators pattern (`run_inventory`/`run_migration`) this
  story mirrors for `run_select`.
- `src/nexus/cli/apps.py` -- where new Typer sub-apps are registered.
- `src/nexus/replatform/models.py` -- `MigrationChecklist`, `ChecklistItem`
  (the input shape).
- `src/nexus/migrate/models.py` (Story 02) -- `Selection`, `SelectionItem`,
  `emit_plan_yaml`.

## Dev Notes

### Modules Affected

- `src/nexus/cli/commands_migrate.py` (new)
- `src/nexus/cli/apps.py` (add `migrate_app`)
- `tests/cli/test_migrate_select_cmd.py` (new)

### Testing Approach

- Typer `CliRunner` end-to-end against a `MigrationChecklist` JSON fixture
  written to `tmp_path`.
- Function-based `test_<func>_<scenario>` tests, e.g.
  `test_run_select_seeds_every_checklist_item_undecided`,
  `test_run_select_missing_checklist_file_exits_1`.
- No mocks; the command reads real files from `tmp_path` -- no
  ServiceNow client is constructed anywhere in this story's code path.
- Assert output YAML text is byte-identical to
  `emit_plan_yaml(expected_selection)` built from Story 02's fakes.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope` (`nexus
  migrate select` bullet), `#Acceptance Criteria` ("select seeds a complete
  selection..." bullet)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 2`
  (plan file is the artifact of record; git PR review is the collaboration
  mechanism)
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Session Decisions`
  (1, Selection UX)
