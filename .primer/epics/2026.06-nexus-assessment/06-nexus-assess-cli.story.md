# Story 06: `nexus assess` CLI -- --for, --job, no-flag + --live/--archive

Status: done
Spec-Clarity: high
Depends-On: 04

## Story

As a NEXUS user,
I want `nexus assess` to expose all three assessment modes from
a single command with predictable flag semantics,
so that `--for <template>` checks readiness, `--job <id>` checks
post-deploy state, and the unflagged form runs a health scan --
all against either an archive (default) or a live re-capture.

## Acceptance Criteria

AC1 (CLI signature):
**Given** `src/nexus/cli/commands_top.py`
**When** the `assess` command is loaded
**Then** the signature is:
```
nexus assess [--for TEMPLATE_ID] [--job JOB_ID] [--live]
             [--archive PATH] [--skip-gate2]
```
Mutual exclusion: `--for` and `--job` cannot both be set.
`--live` and `--archive` cannot both be set. `--skip-gate2` only
meaningful with `--job` (warning if used elsewhere).

AC2 (--for invokes Gate1Readiness):
**Given** `nexus assess --for acme-template --archive /tmp/cap.yaml`
**When** the command runs
**Then** the CLI:
1. Loads the archive via `ArchiveReader.read(path)` -> CaptureResult
2. Loads the matching ruleset:
   `load_ruleset(templates/assessments/<resolved-slug>.yaml)`
3. Constructs `GateContext(capture, apply_result=None, phase=PRE_APPLY)`
4. Invokes `Gate1Readiness(ruleset, "acme-template").evaluate(ctx)`
5. Calls `render_report(report, render_context)`
6. Exits 2 on `verdict=BLOCK`, 1 on `verdict=ERROR`, 0 on `verdict=PASS`

AC3 (--for ruleset resolution):
**Given** `--for acme-template`
**When** the CLI resolves the ruleset
**Then** it scans `templates/assessments/*.yaml`, parses each
via `load_ruleset`, and selects rulesets where
`"acme-template" in ruleset.applies_to`. If multiple rulesets
match, all are merged (rules concatenated). If none match,
exit 1 with Notice.error("no readiness ruleset for template
acme-template").

AC4 (--job invokes Gate2Validation):
**Given** `nexus assess --job <job-id> --live`
**When** the command runs
**Then** the CLI:
1. Reads the apply job log (stub for now -- this story creates
   `_load_apply_result(job_id) -> ApplyResult` helper returning
   an empty ApplyResult; Template Library epic will implement
   the actual log reader)
2. Re-captures live via `CaptureEngine.capture(...)` using the
   scope from the apply log (stub: passes empty CaptureResult
   when log reader stubbed)
3. Constructs `GateContext(capture, apply_result, phase=POST_APPLY)`
4. Invokes `Gate2Validation(ruleset, template_id_from_log).evaluate(ctx)`
5. Renders + exits with same code mapping as AC2

AC5 (--job + --skip-gate2):
**Given** `nexus assess --job <id> --skip-gate2`
**When** the command runs
**Then** the CLI exits 0 with Notice.warning("Gate 2 skipped by
--skip-gate2"). Useful as a placeholder for the apply
orchestrator which sets it.

AC6 (no flags = HealthScan):
**Given** `nexus assess` (no `--for`, no `--job`)
**When** the command runs against the default archive
**Then** the CLI:
1. Loads the archive (from `--archive PATH` or default location)
2. Loads ALL rulesets from `templates/assessments/*.yaml`
3. Constructs `GateContext(capture, apply_result=None,
   phase=STANDALONE)`
4. Invokes `HealthScan(merged_ruleset).evaluate(ctx)`
5. Renders + exits with verdict code mapping

AC7 (--live):
**Given** `--live` flag
**When** the CLI runs
**Then** instead of `ArchiveReader.read(...)`, it invokes
`CaptureEngine.capture(...)` with the appropriate scope.
For `--for <template>`, scope = template's target scope (read
from template manifest). For no-flag (health), scope = current
active connection's default. For `--job`, scope = scope from
apply log.

AC8 (default archive resolution):
**Given** no `--archive PATH` provided
**When** the CLI runs without `--live`
**Then** it reads from `paths.default_capture_archive_path()` --
the most-recent archive in `paths.archive_dir / "captures/*.yaml"`
selected by mtime. If none exists, exit 1 with
Notice.error("no archive found; run `nexus capture` first or
pass --live").

AC9 (--for + --job mutex):
**Given** both `--for` and `--job` set
**When** the CLI runs
**Then** raises `typer.BadParameter` -> exit 2 with
clear "Cannot use --for and --job together" message.

AC10 (--live + --archive mutex):
**Given** both `--live` and `--archive` set
**When** the CLI runs
**Then** raises `typer.BadParameter` -> exit 2.

AC11 (exit code table):
**Given** all three verdict values + setup errors
**When** the CLI runs
**Then** exit codes follow:
- `verdict=PASS` -> 0
- `verdict=BLOCK` -> 2 (matches InteractiveRequiredError precedent)
- `verdict=ERROR` -> 1
- Setup error (no ruleset, no archive) -> 1
- BadParameter (flag mutex) -> 2

AC12 (smoke test):
**Given** a single fixture: a real ruleset YAML + a real archive
YAML
**When** the smoke test runs `nexus assess --for fixture-template
--archive <path>`
**Then** the process exits with the expected code and stdout
contains the expected verdict badge.

## Must NOT

* Must NOT implement the apply log reader fully -- that's
  Template Library epic. Stub `_load_apply_result(job_id)` is
  enough for this story.
* Must NOT couple to a specific archive directory layout --
  use `paths.NexusPaths` (existing).
* Must NOT inline the rendering -- call `render_report` from
  Story 05.
* Must NOT use `sys.exit`. Raise `typer.Exit(N)`.
* Must NOT add a `--fix` flag or any remediation action.

## Tasks / Subtasks

* [ ] Edit `src/nexus/cli/commands_top.py:assess()` -- full
      implementation (AC1)
* [ ] Implement archive vs live resolution helper in
      `src/nexus/cli/commands_assess.py` (new) or inline (AC7, AC8)
* [ ] Implement ruleset resolution: `_resolve_rulesets_for_template`
      and `_load_all_rulesets` (AC3, AC6)
* [ ] Wire to `Gate1Readiness` (AC2)
* [ ] Stub `_load_apply_result(job_id) -> ApplyResult` -- returns
      empty ApplyResult; raises NotImplementedError if `--job` AND
      `--live` is set AND --skip-gate2 not set (deferred to
      Template Library epic; this story just plumbs the path)
* [ ] Wire to `Gate2Validation` with `--skip-gate2` short-circuit (AC4, AC5)
* [ ] Wire to `HealthScan` (AC6)
* [ ] Flag mutex validation (AC9, AC10)
* [ ] Exit-code mapping (AC11)
* [ ] Update help text in `cli/help_text.py`
* [ ] Smoke test script (AC12)
* [ ] Create `tests/test_cli_assess_for_template.py` (AC2, AC3, AC7)
* [ ] Create `tests/test_cli_assess_job.py` (AC4, AC5)
* [ ] Create `tests/test_cli_assess_health.py` (AC6, AC8)
* [ ] Create `tests/test_cli_assess_flag_mutex.py` (AC9, AC10)
* [ ] Create `tests/test_cli_assess_exit_codes.py` (AC11)

## Existing Code

* `src/nexus/cli/commands_top.py:132-148` -- `assess` command
  stub (raises NotImplementedError today)
* `src/nexus/capture/archive_reader.py:ArchiveReader.read`
* `src/nexus/capture/engine.py:CaptureEngine.capture`
* `src/nexus/config/paths.py:NexusPaths`
* Stories 01-05: schemas, engine, gates, reporter, loader
* `src/nexus/cli/console.py:get_render_context`
* `src/nexus/cli/help_text.py`

## Dev Notes

### Modules Affected

* `src/nexus/cli/commands_top.py` (or new `commands_assess.py` --
  extract for file-size budget)
* `src/nexus/cli/help_text.py`
* `src/nexus/config/paths.py` (add `default_capture_archive_path`
  if not present)
* `tests/test_cli_assess_*.py` (5 files)
* `scripts/smoke_assess.py` (new, optional -- mirror
  smoke_plugins.py pattern if it exists)

### Testing Approach

* CLI tests use Typer's `CliRunner` with overridden `Gate1Readiness`,
  `Gate2Validation`, `HealthScan` via dependency injection
  (factory pattern), OR extract a `_main(args, gates_factory,
  render_context)` helper for direct invocation. Mirror
  `commands_plugins_exec.py` test pattern.
* Use `FakeCaptureResult`, `FakeRuleset`, `FakeGate` from earlier
  stories.
* AC12 smoke test invokes the real subprocess (`nexus assess
  --for <fixture> --archive <fixture>`) and asserts on exit code
  + stdout. One smoke case, not per-AC.

### Conventions

* Typer commands -- existing patterns
* Exit codes via `typer.Exit(N)` only
* Help text in `cli/help_text.py` per project convention

## References

* PRD: `.primer/prd/PRD-002-nexus-assessment.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-assessment-rule-engine.md#Recommendation 5`
* Precedent: `src/nexus/cli/commands_plugins_exec.py`
* Stories 01-05
