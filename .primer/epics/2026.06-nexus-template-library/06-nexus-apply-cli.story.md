# Story 06: `nexus apply <template>` CLI orchestrator -- wires Gate 1 + ApplyEngine + Gate 2

Status: backlog
Spec-Clarity: high
Depends-On: 05

## Story

As a NEXUS user,
I want `nexus apply <template-id> [--scope X] [--force] [--skip-gate2]`
to capture pre-state, run Gate 1, apply the template, recapture
post-state, and run Gate 2,
so that one command deploys a template safely and refuses to apply
when readiness checks fail.

## Acceptance Criteria

AC1 (CLI signature):
**Given** `src/nexus/cli/commands_top.py`
**When** the `apply` command body is loaded
**Then** the signature accepts:
* `template` (positional, required): template id resolving to
  `paths.templates_dir / <template> / template.yaml`
* `--scope X`: optional override for template's `target_scope` field
* `--force`: skip Gate 1 BLOCK verdict (not ERROR)
* `--skip-gate2`: run apply but skip post-apply recapture + Gate 2
* `--dry-run`: stays NotImplementedError stub for v1

AC2 (happy path -- PASS through both gates):
**Given** a template whose readiness ruleset passes Gate 1 and
post-apply Gate 2
**When** `nexus apply <id>` runs against a wired SN client
**Then** the orchestrator:
1. Resolves the template path.
2. Runs `capture_live(target_scope)` -> pre-CaptureResult.
3. Calls `Gate1Readiness.evaluate(GateContext(pre, None, PRE_APPLY))`;
   verdict=PASS.
4. Calls `ApplyEngine.apply(template_path)` -> ApplyResult.
5. Runs `capture_live(target_scope)` -> post-CaptureResult.
6. Calls `Gate2Validation.evaluate(GateContext(post, apply_result,
   POST_APPLY))`; verdict=PASS.
7. Renders the final GateReport.
8. Exits 0.

AC3 (Gate 1 BLOCK without --force):
**Given** a template whose Gate 1 ruleset returns BLOCK
**When** `nexus apply <id>` runs (no --force)
**Then** the orchestrator exits 2 BEFORE calling ApplyEngine.apply.
Notice + Hint("--force") shown. No write to SN.

AC4 (Gate 1 BLOCK with --force):
**Given** the same template
**When** `nexus apply <id> --force` runs
**Then** the orchestrator continues to ApplyEngine.apply. The
Gate 1 findings are still rendered as a Notice.warn (not silenced).

AC5 (Gate 1 ERROR -- --force does NOT skip):
**Given** a template whose Gate 1 returns ERROR (capture
incomplete, ruleset load failed, etc.)
**When** `nexus apply <id> --force` runs
**Then** the orchestrator exits 1. The --force flag explicitly
does NOT bypass ERROR. Notice.error shown.

AC6 (Gate 2 BLOCK after apply):
**Given** ApplyEngine.apply succeeded but Gate 2 returns BLOCK
**When** the orchestrator handles the post-gate verdict
**Then** the orchestrator exits 2. The ApplyResult is still
reported (the apply already wrote to SN; cannot un-do).

AC7 (Gate 2 ERROR after apply):
**Given** post-apply recapture fails (live capture timeout)
**When** `Gate2Validation.evaluate(...)` returns ERROR
**Then** the orchestrator exits 1 with a Notice pointing at
`nexus assess --job <ApplyResult.update_set_sys_id> --live` for
retry.

AC8 (--skip-gate2):
**Given** `nexus apply <id> --skip-gate2`
**When** the orchestrator runs
**Then** after ApplyEngine.apply succeeds, NO recapture and NO
Gate 2 evaluation. Render apply_result with a Notice.warn
("Gate 2 skipped by --skip-gate2"). Exit 0.

AC9 (--scope override):
**Given** a template declaring `target_scope: "global"` and the
CLI invocation `nexus apply <id> --scope x_my_app`
**When** ApplyEngine resolves the scope
**Then** the effective scope is `x_my_app`, NOT `"global"`. The
ApplyResult.target_scope_sys_id reflects the override.

AC10 (template id resolution):
**Given** a template id that does not exist under `paths.templates_dir`
**When** the CLI runs
**Then** exit 1 with Notice.error("template id %r not found in
templates_dir") and a Hint pointing at `nexus sync`.

AC11 (verdict -> exit-code mapping):
**Given** all combinations of Gate 1 and Gate 2 verdicts
**When** the orchestrator returns
**Then**:
* Gate 1 PASS + Gate 2 PASS -> exit 0
* Gate 1 BLOCK + no --force -> exit 2
* Gate 1 BLOCK + --force + Gate 2 PASS -> exit 0
* Gate 1 BLOCK + --force + Gate 2 BLOCK -> exit 2
* Gate 1 ERROR (any) -> exit 1
* Gate 2 ERROR (any) -> exit 1
* Apply itself fails (ScopeNotFoundError, etc.) -> exit 1

AC12 (testable via injected collaborators):
**Given** `src/nexus/cli/commands_apply.py:run_apply(...)`
**When** tests inject fakes
**Then** the dispatcher accepts an `ApplyCollaborators` bundle
(mirror Assessment's pattern) with `capture_runner`,
`apply_engine_factory`, `gate1_factory`, `gate2_factory`. Tests
substitute fakes for each; production `default_collaborators(paths)`
wires real implementations.

AC13 (wires Assessment's stubs):
**Given** Assessment Story 06's `apply_result_loader` callable
**When** Story 06 of this epic ships
**Then** a real implementation is provided that reads
`paths.jobs_dir / <job_id> / apply.jsonl` and reconstructs the
ApplyResult + extracts the template_id for Gate 2 evaluation.
The `capture_runner` stub in `commands_assess.py` also gets a
real implementation (invokes CaptureEngine.capture).

AC14 (type strictness):
**Given** the new file
**When** pyright strict + mypy strict run
**Then** 0 errors. No `# type: ignore`.

## Must NOT

* Must NOT call `sys.exit` directly. Raise `typer.Exit(N)`.
* Must NOT bypass Gate 1 ERROR via --force.
* Must NOT swallow exceptions from ApplyEngine.apply -- let them
  propagate or convert to a clear Notice.error + exit 1.
* Must NOT duplicate verdict-to-exit logic; reuse the mapping
  from Assessment Story 06 (`_render_and_exit`).
* Must NOT add a `--rollback` flag (out of scope; rollback engine
  is a separate epic).
* Must NOT change `nexus assess` behavior; the Assessment CLI
  continues to work standalone.

## Tasks / Subtasks

* [ ] Create `src/nexus/cli/commands_apply.py` -- ApplyCollaborators
      bundle + `run_apply(...)` dispatcher (AC12, AC14)
* [ ] Replace `src/nexus/cli/commands_top.py:apply()` body with a
      thin wrapper calling `run_apply(...)` (AC1, AC9, AC10)
* [ ] Wire Gate 1 + ApplyEngine + Gate 2 sequence (AC2-AC8)
* [ ] Implement Assessment's `apply_result_loader` stub in
      `commands_assess.py` (read jobs_dir/<job_id>/apply.jsonl) (AC13)
* [ ] Implement Assessment's `capture_runner` stub
      (invoke CaptureEngine) (AC13)
* [ ] Apply verdict-to-exit mapping (AC11)
* [ ] Create `tests/templates/test_cli_apply_happy_path.py` (AC2, AC9)
* [ ] Create `tests/templates/test_cli_apply_gate1_block.py` (AC3, AC4)
* [ ] Create `tests/templates/test_cli_apply_gate1_error.py` (AC5)
* [ ] Create `tests/templates/test_cli_apply_gate2_block_error.py` (AC6, AC7)
* [ ] Create `tests/templates/test_cli_apply_skip_gate2.py` (AC8)
* [ ] Create `tests/templates/test_cli_apply_template_not_found.py` (AC10)
* [ ] Create `tests/templates/test_cli_apply_exit_codes.py` (AC11)
* [ ] Update `src/nexus/cli/help_text.py`
* [ ] Update `.ratchet.json` baselines

## Existing Code

* Story 05 -- ApplyEngine, ApplyResult, AppliedRecord
* Assessment epic:
  - `src/nexus/assessment/gates/readiness.py:Gate1Readiness`
  - `src/nexus/assessment/gates/validation.py:Gate2Validation`
  - `src/nexus/assessment/context.py:GateContext`
  - `src/nexus/assessment/reporter.py:render_report`
  - `src/nexus/cli/commands_assess.py:apply_result_loader,
    capture_runner` (stubs to wire)
* `src/nexus/capture/engine.py:CaptureEngine` -- the live-capture
  primitive
* `src/nexus/ui/components/batch_progress.py:BatchProgressProtocol`
  -- per-record progress

## Dev Notes

### Modules Affected

* `src/nexus/cli/commands_apply.py` (new -- mirror commands_assess.py)
* `src/nexus/cli/commands_top.py` (thin wrapper)
* `src/nexus/cli/commands_assess.py` (wire the previously-stubbed
  apply_result_loader and capture_runner)
* `src/nexus/cli/help_text.py`
* `tests/templates/test_cli_apply_*.py` (7 files)

### Testing approach

* Use Assessment's `AssessCollaborators` pattern -- inject every
  I/O boundary as a callable. Production wires real implementations;
  tests inject `FakeApplyEngine`, `FakeGate`, fake `capture_runner`
  returning a canned `CaptureResult`.
* Each AC -> at least one focused test.
* Smoke test optional (covered by the per-AC tests).

### Conventions

* Typer command body -- thin wrapper; logic in `run_apply`.
* Exit codes via `typer.Exit(N)`.
* `match`/`case` over `GateVerdict` with `case _:` default + pragma.
* Deferred imports in commands_top.py per ADR-022.

## References

* Story 05 (ApplyEngine)
* PRD: `.primer/prd/PRD-003-nexus-template-library.md#In Scope`
* Brainstorming: `.primer/brainstorming/2026-05-19-nexus-template-library.md#Recommendation 7`
* Reference: `src/nexus/cli/commands_assess.py` (mirror dispatcher pattern)
* ADR-003: 3-gate assessment model
