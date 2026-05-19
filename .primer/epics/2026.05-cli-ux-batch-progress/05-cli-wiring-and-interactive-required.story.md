# Story 05: Wire CLI + InteractiveRequiredError exit-2 + ADR finalize

Status: ready
Spec-Clarity: high
Depends-On: 04

## Story

As a NEXUS user invoking `nexus plugins upgrade <id>` or
`nexus plugins upgrade --family X`,
I want the right progress display for my terminal to actually
appear,
so that the substrate, protocol, and executor refactor we just
landed start showing real value.

## Acceptance Criteria

AC1 (single-item upgrade wired):
**Given** `nexus plugins upgrade plugin.a` invoked on RICH
profile
**When** the command runs
**Then** a Rich progress bar tracking SN's reported percent with
WeightedETA column is rendered. On completion, the Live region
tears down cleanly and a summary Notice prints.

AC2 (batch upgrade wired):
**Given** `nexus plugins upgrade --family X --yes` on RICH
profile with N >= 2 targets
**When** the command runs
**Then** an overall progress bar (M of N, weighted ETA) plus a
transient per-item bar are rendered. Each item's completion
removes its transient bar and advances the overall.

AC3 (LEGACY/PLAIN line-mode):
**Given** the same commands invoked on LEGACY or PLAIN profile
**When** the commands run
**Then** progress is rendered as one line per event via
`PlainBatchProgress`. No Live region, no `\r`.

AC4 (InteractiveRequiredError exit-2):
**Given** `nexus plugins upgrade --family X` (NO `--yes`) on
PLAIN profile
**When** the command runs
**Then** the process exits with code 2, stderr contains
`Notice.error("Interactive confirmation required ...")`, and a
Hint pointing at `--yes` for non-interactive use.

AC5 (InteractiveRequiredError class):
**Given** `src/nexus/cli/errors.py` (or extension of existing
errors module)
**When** the file exists
**Then** it exports `class InteractiveRequiredError(Exception)`
with `exit_code: int = 2` class attribute, and the CLI command
catches it (or raises `typer.Exit(2)`) at the boundary.

AC6 (no InteractiveRequiredError on RICH/BASIC/LEGACY):
**Given** the same `--family X` command (no `--yes`) on any
non-PLAIN profile
**When** the command runs
**Then** the existing interactive confirmation prompt fires; if
the user confirms, the batch proceeds; if the user declines,
exit-0 is returned. Existing behavior preserved.

AC7 (single-item upgrade with --yes on PLAIN is OK):
**Given** `nexus plugins upgrade plugin.a --yes` on PLAIN
**When** the command runs
**Then** it proceeds with PlainBatchProgress output. No
InteractiveRequiredError raised.

AC8 (--all also gated):
**Given** `nexus plugins upgrade --all` (no `--yes`) on PLAIN
**When** the command runs
**Then** `InteractiveRequiredError` raised, exit code 2.

AC9 (ADR finalized):
**Given** Story 00 drafted
`.primer/adr/ADR-NNN-framedviewer-supersedes-pypager.md` with
Status: proposed
**When** Story 05 ships
**Then** the ADR Status is updated to `Accepted` with the
acceptance date. Story 05 is the last story in the epic, so the
ADR is finalized here.

AC10 (no regressions):
**Given** the full test suite + smoke-tests
**When** Story 05 ships
**Then** all pass; pyright + mypy + ruff + black 0 errors; 100%
line coverage on every new and modified module.

## Must NOT

* Must NOT change the existing positional surface of `nexus
  plugins upgrade <id>`. Only new behavior is the progress
  display.
* Must NOT use `sys.exit` directly. Raise `InteractiveRequiredError`
  and let Typer's exception handler convert to exit code, OR
  raise `typer.Exit(2)` directly. Pick whichever path the
  existing cli/ errors handling uses.
* Must NOT mix InteractiveRequiredError with `typer.Exit(1)`
  (general error). Exit-2 is distinct and means usage error.
* Must NOT skip the smoke test. The whole point of this story is
  proving the stack end-to-end.

## Tasks / Subtasks

* [ ] Audit existing exit-code usage:
      `grep -rn "typer.Exit\|sys.exit" src/nexus/cli/`
* [ ] Create or extend `src/nexus/cli/errors.py`:
  * [ ] `class InteractiveRequiredError(Exception)` with
        `exit_code: int = 2`
  * [ ] Optional: register a handler on the root Typer app that
        catches `InteractiveRequiredError` and calls
        `typer.Exit(2)` -- check existing pattern first
* [ ] Edit `src/nexus/cli/commands_plugins_exec.py`:
  * [ ] In `plugins_upgrade` for single-item path:
        `with make_batch_progress(ctx, total=1, store=
        EmaPriorStore(cache_path=paths.eta_prior_cache_path()))
        as bp: executor.upgrade(plugin_id, progress=bp)`
  * [ ] In `plugins_upgrade` for `--family` and `--all` paths:
        `with make_batch_progress(ctx, total=len(targets),
        store=...) as bp: executor.batch_upgrade(targets,
        progress=bp)`
  * [ ] Before opening the context manager, if profile is PLAIN
        and `--yes` not provided: raise
        `InteractiveRequiredError("Interactive confirmation
        required ...")`
* [ ] Edit `src/nexus/cli/commands_plugins_outdated.py` if the
      `outdated` command has its own upgrade trigger; otherwise
      no edit needed
* [ ] Update `src/nexus/adr/ADR-NNN-...md` Status to Accepted
* [ ] Create `tests/test_cli_plugins_upgrade_with_progress.py`:
  * [ ] `test_plugins_upgrade_single_renders_progress_on_rich_profile`
  * [ ] `test_plugins_upgrade_family_yes_runs_batch_progress`
  * [ ] `test_plugins_upgrade_family_without_yes_on_plain_raises_exit_2`
  * [ ] `test_plugins_upgrade_all_without_yes_on_plain_raises_exit_2`
  * [ ] `test_plugins_upgrade_yes_on_plain_proceeds_with_plain_progress`
  * [ ] `test_plugins_upgrade_without_yes_on_rich_prompts_confirmation`
* [ ] Add smoke test entry in `scripts/smoke_plugins.py` (if the
      script exists -- otherwise no-op for this AC):
  * [ ] `nexus plugins upgrade <id> --yes` -- verify exit 0 +
        non-empty progress output
* [ ] Update `.ratchet.json` baselines for modified modules

## Existing Code

* `src/nexus/cli/commands_plugins_exec.py` -- the `upgrade`
  command implementation
* `src/nexus/cli/commands_plugins_outdated.py` -- where
  `outdated --apply` would have lived; current behavior is
  read-only listing, so no wiring needed unless `outdated`
  triggers an upgrade
* `src/nexus/cli/console.py:render_context` -- shared
* `src/nexus/cli/errors.py` -- existing exception module (if
  any); otherwise create
* `src/nexus/config/paths.py:NexusPaths.eta_prior_cache_path` --
  added by Story 01

## Dev Notes

### Wire-up sketch

```python
@plugins_app.command("upgrade")
def plugins_upgrade(
    plugin_id: str | None = typer.Argument(None),
    family: str | None = typer.Option(None, "--family"),
    all_: bool = typer.Option(False, "--all"),
    yes: bool = typer.Option(False, "--yes"),
    ctx: typer.Context = ...,
) -> None:
    rctx = get_render_context(ctx)
    targets = _resolve_targets(plugin_id, family, all_)
    if (family or all_) and not yes and rctx.profile is RenderProfile.PLAIN:
        raise InteractiveRequiredError(
            "Interactive confirmation required; pass --yes for non-interactive batch upgrades."
        )
    if (family or all_) and not yes:
        if not typer.confirm(...):
            return
    paths = NexusPaths.from_env()
    store = EmaPriorStore(cache_path=paths.eta_prior_cache_path())
    with make_batch_progress(rctx, total=len(targets), store=store) as bp:
        if len(targets) == 1:
            executor.upgrade(targets[0].plugin_id, progress=bp)
        else:
            executor.batch_upgrade(targets, progress=bp)
```

(Exact target-resolution and result-handling code mirrors the
existing implementation.)

### Test approach -- driving the command

The function-style command can be invoked directly with a
hand-built Typer context. Use the project's existing pattern from
`tests/test_cli_setup.py` -- `_main` helpers receive injected
collaborators. If `plugins_upgrade` does not already factor out a
`_main`, extracting one is part of this story's tasks. Otherwise
test via `CliRunner` with overridden `make_batch_progress` (return
a `FakeBatchProgress`) and overridden `EmaPriorStore`.

### Smoke test note

If `scripts/smoke_plugins.py` exists, append a single case. If it
doesn't, skip without failing the AC -- the unit tests cover the
contract.

## References

* PRD: `.primer/prd/PRD-001-cli-ux-wow-factor.md` (Wiring +
  InteractiveRequiredError sections + exit-code revision)
* Original story:
  `.primer/stories/2026.05.02-cli-batch-progress-eta.md` (Tasks
  6, 7, 14, 15)
* Brainstorming: `.primer/brainstorming/2026-05-18-cli-ux-implementation-plan.md`
* Setup epic precedent: `.primer/epics/2026.05-nexus-setup-wizard/`
  (Typer wrapper + `_main` helper pattern)
* Sync epic precedent: `.primer/epics/2026.05-nexus-sync-catalog/`
  (CLI testing approach)
