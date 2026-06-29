# Story 06: `nexus assess inventory` + `nexus assess migration`

Status: backlog
Spec-Clarity: high
Depends-On: 02, 03, 04, 05

## Story

As a Solution Consultant driving a replatform,
I want `nexus assess inventory` and `nexus assess migration` subcommands,
so that I can inventory one instance and emit a bi-directional build checklist
from the CLI.

## Acceptance Criteria

AC1 (collaborators via ctx.obj):
**Given** the `assess` group callback (Story 05)
**When** it runs
**Then** it attaches a `ReplatformCollaborators` bundle (capture/archive
resolvers, classifier, diff, reporter) to `ctx.obj`, and the subcommand bodies
read it from `ctx.obj` -- no global state, fakes injectable in tests.

AC2 (inventory subcommand):
**Given** `nexus assess inventory <profile> [--from-archive P] [--out inv.json]`
**When** run
**Then** it resolves a `CaptureResult` (explicit `--from-archive`, else newest
archive for the profile), calls `classify(...)`, and renders the
`UseCaseInventory`; with `--out` it writes the inventory as JSON. Exit 0 on
success, 1 when no capture is found.

AC3 (migration subcommand):
**Given** `nexus assess migration --from <old> --to <new> [--from-archive P]
[--to-archive P] [--scope-alias OLD=NEW ...] [--out checklist.md]`
**When** run
**Then** it classifies both instances, calls `build_checklist(source, target,
aliases)`, and renders the `MigrationChecklist`; with `--out` it writes
markdown via the Story 04 emitter. Exit 0 on success.

AC4 (scope-alias parsing):
**Given** `--scope-alias x_old=x_new` (repeatable)
**When** parsed
**Then** each `OLD=NEW` becomes a `(OLD, NEW)` tuple passed to
`build_checklist`; a malformed value (no `=`) raises `typer.BadParameter`.

AC5 (advisory only):
**Given** either subcommand
**When** run
**Then** it performs NO write to either ServiceNow instance -- output is
console and/or local files only.

AC6 (gates still intact):
**Given** the new subcommands are registered
**When** bare `nexus assess` / `--for` / `--job` run
**Then** they behave exactly as before (Story 05 regression still green).

## Must NOT

- Must NOT write to any ServiceNow instance (advisory only; charter limit).
- Must NOT call the Anthropic API or any MCP tool from these commands.
- Must NOT duplicate classification logic -- reuse Story 02 `classify`.
- Must NOT change gate/health behavior (Story 05 owns the group).

## Tasks / Subtasks

- [ ] Define `ReplatformCollaborators` + `default_replatform_collaborators(paths)` (AC1)
- [ ] Attach collaborators to `ctx.obj` in the assess group callback (AC1)
- [ ] Implement `inventory` subcommand body + `--out inv.json` (AC2)
- [ ] Implement `migration` subcommand body + markdown `--out` (AC3)
- [ ] Add `--scope-alias` parser -> tuple of pairs (AC4)
- [ ] Create `tests/test_assess_inventory_cmd.py` + `tests/test_assess_migration_cmd.py`
      using `CliRunner` + fakes (AC2-AC6)

## Existing Code

- `src/nexus/cli/commands_assess.py` / assess group (Story 05).
- `src/nexus/replatform/{classifier,diff,reporter}.py` (Stories 02-04).
- `src/nexus/capture/archive.py` -- `ArchiveReader`; `commands_capture.py` --
  archive-resolution reference.
- `src/nexus/instances/registry.py` -- profile resolution.

## Dev Notes

### Modules Affected

- `src/nexus/cli/commands_assess.py` (or `cli/assess_app.py`) -- subcommand bodies
- `tests/test_assess_inventory_cmd.py`, `tests/test_assess_migration_cmd.py`

### Testing Approach

- Typer `CliRunner` end-to-end against `FakeCaptureResult` /
  `FakeUseCaseInventory` injected through `ctx.obj`.
- Assert `--out` writes the expected JSON / markdown to `tmp_path`.
- Assert no ServiceNow write path is reached (advisory).
- Regression: bare assess paths still pass.

### Conventions

- Collaborator-injection pattern (mirrors `AssessCollaborators`), but via
  `ctx.obj` for group subcommands.
- ASCII only; no-backward-compat; file header + Google docstrings + `__all__`.

## References

- PRD: `.primer/prd/PRD-004-nexus-replatform-checklist.md#In Scope`
- Brainstorming: `.primer/brainstorming/2026-06-29-nexus-assess-migration.md#Recommendation 8`
- ADR: `.primer/adr/ADR-025-replatform-cross-instance-analysis.md#Decision 3`
- Existing: `src/nexus/cli/commands_assess.py`, `src/nexus/capture/archive.py`
