# Story 05: convert `assess` to a Typer group (preserve gates)

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a NEXUS maintainer adding replatform subcommands,
I want `nexus assess` restructured from a leaf command into a Typer group,
so that new subcommands attach cleanly while the existing gate/health UX is
preserved.

## Acceptance Criteria

AC1 (group with preserved bare behavior):
**Given** `nexus assess` is registered as a Typer group with a callback using
`invoke_without_command=True`
**When** `nexus assess` is run with no subcommand (optionally `--for`,
`--job`, `--live`, `--archive`)
**Then** the callback guards on `if ctx.invoked_subcommand is None:` and runs
the existing `run_assess(...)` gate/health path exactly as before, returning
the same exit codes (PASS 0, BLOCK 2, ERROR 1).

AC2 (no double-fire):
**Given** a subcommand IS provided (e.g. a placeholder `noop` in tests, or the
real subcommands from Story 06)
**When** invoked
**Then** the bare gate/health path does NOT run -- only the subcommand body
executes, and exactly one exit code is returned.

AC3 (commands_top wiring):
**Given** `commands_top.py` previously called `run_assess(...)` directly
**When** restructured
**Then** it registers the `assess` Typer group (e.g.
`app.add_typer(assess_app, name="assess")`) and no longer invokes
`run_assess` as a bare leaf command.

AC4 (regression -- gate behavior unchanged):
**Given** the existing assess test suite
**When** run after the restructure
**Then** all existing `nexus assess --for` / `--job` / bare-health tests pass
unchanged (only invocation wiring may be updated, not asserted behavior).

AC5 (flag mutex preserved):
**Given** `--for` and `--job` together, or `--live` and `--archive` together
**When** bare `assess` runs
**Then** `typer.BadParameter` is still raised (existing `_validate_flag_mutex`).

## Must NOT

- Must NOT change the verdict-to-exit-code mapping or the gate logic.
- Must NOT introduce a backward-compat shim or alias for the old leaf form --
  fully migrate call sites (no-backward-compat rule).
- Must NOT add the replatform subcommands here -- that is Story 06.
- Must NOT alter `RuleEngine`, gates, or `assessment/` internals.

## Tasks / Subtasks

- [ ] Add a `assess` Typer sub-app object (location: `commands_assess.py` or a
      new `cli/assess_app.py`) with an `invoke_without_command=True` callback (AC1)
- [ ] Move the bare gate/health dispatch into the callback behind the
      `ctx.invoked_subcommand is None` guard (AC1, AC2)
- [ ] Update `commands_top.py` to register the group (AC3)
- [ ] Update/extend tests: bare-path regression + a placeholder subcommand to
      prove no double-fire (AC2, AC4)
- [ ] Verify flag mutex still enforced (AC5)

## Existing Code

- `src/nexus/cli/commands_assess.py` -- `run_assess(...)`,
  `_validate_flag_mutex`, `default_collaborators`, verdict-to-exit mapping.
- `src/nexus/cli/commands_top.py` -- current direct call site for assess.

## Dev Notes

### Modules Affected

- `src/nexus/cli/commands_assess.py` (or new `cli/assess_app.py`)
- `src/nexus/cli/commands_top.py`
- `tests/` -- existing assess command tests + a new no-double-fire test

### Testing Approach

- Use Typer's `CliRunner` to invoke `nexus assess` bare and with a placeholder
  subcommand; assert single exit code and correct path.
- Keep existing assess tests green (regression gate).

### Conventions

- Typer group callback pattern; `ctx: typer.Context`.
- No-backward-compat: remove the old leaf registration entirely.
- File header + Google docstrings + `__all__`.

## References

- PRD: `.primer/prd/PRD-004-nexus-replatform-checklist.md#In Scope`
- Brainstorming: `.primer/brainstorming/2026-06-29-nexus-assess-migration.md#Recommendation 8`
- ADR: `.primer/adr/ADR-025-replatform-cross-instance-analysis.md#Decision 4`
- Existing: `src/nexus/cli/commands_assess.py`, `src/nexus/cli/commands_top.py`
