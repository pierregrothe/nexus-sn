# Story 04: PluginExecutor.upgrade + batch_upgrade progress kwarg refactor

Status: ready
Spec-Clarity: high
Depends-On: 03

## Story

As a CLI command author wiring a progress display,
I want `PluginExecutor.upgrade` and `PluginExecutor.batch_upgrade`
to accept an optional `progress: BatchProgressProtocol | None`,
so that I can drive the display from inside the executor without
the executor knowing what kind of display it is.

## Acceptance Criteria

AC1 (progress kwarg on upgrade):
**Given** `PluginExecutor.upgrade(plugin_id: str, ...)`
**When** Story 04 ships
**Then** the signature gains
`progress: BatchProgressProtocol | None = None` as a
keyword-only argument (after `*`).

AC2 (progress kwarg on batch_upgrade):
**Given** `PluginExecutor.batch_upgrade(targets, families=(), ...)`
**When** Story 04 ships
**Then** the signature gains
`progress: BatchProgressProtocol | None = None` as a
keyword-only argument.

AC3 (None preserves today's behavior):
**Given** any existing call site (cli/commands_plugins_exec.py,
cli/commands_plugins_outdated.py, scripts/smoke_*.py)
**When** the same call is made without `progress=`
**Then** the executor's behavior is byte-identical to today:
same console output, same OperationResult shape, same exit
semantics.

AC4 (single-item upgrade with progress):
**Given** `executor.upgrade("plugin.a", progress=bp)` where
`bp = FakeBatchProgress(...)`
**When** the executor runs to success
**Then** `bp.recorded_calls` contains, in order:
1. `("start_batch", {"total": 1})`
2. `("start_item", {"plugin_id": "plugin.a", "family": "..."})`
3. one or more `("update_item", {"task_id": ..., "sn_pct":
   N})` per ProgressPoller cycle
4. `("finish_item", {"task_id": ..., "duration_s": F,
   "family": "...", "success": True})`

AC5 (single-item upgrade with progress, failure path):
**Given** `executor.upgrade("plugin.a", progress=bp)` where the
plugin upgrade fails
**When** the executor encounters the failure
**Then** the final recorded call is `("finish_item",
{"task_id": ..., "duration_s": F, "family": "...", "success":
False})`.

AC6 (batch_upgrade with progress):
**Given** `executor.batch_upgrade([t1, t2], progress=bp)` where
both succeed
**When** the executor runs
**Then** `bp.recorded_calls` shows:
1. `start_batch(total=2)`
2. for each target: `start_item`, one or more `update_item`,
   `finish_item(success=True)`

AC7 (batch_upgrade skip-on-fail preserved):
**Given** `executor.batch_upgrade([t1, t2], progress=bp)` where
t1 fails, t2 succeeds
**When** the executor runs
**Then** t1 records `finish_item(success=False)`, then t2 starts
and records `finish_item(success=True)`. Batch does not abort on
t1's failure (today's behavior).

AC8 (output routing):
**Given** `executor.batch_upgrade(..., progress=bp)`
**When** the executor would call `self._console.print("...")`
today
**Then** the call is routed through `progress.console.print(...)`
instead. This is the load-bearing piece for Rich Live region
co-existence -- direct `console.print` would corrupt the Live
region.

AC9 (no console parameter break):
**Given** existing call sites pass `console=some_console`
**When** Story 04 ships
**Then** the `console` parameter is unchanged. When progress is
None, output continues to flow through `console`. When progress
is provided, output flows through `progress.console`.

AC10 (no progress callback double-emission):
**Given** the executor's existing `ProgressCallback` extension
point
**When** progress is set
**Then** the executor's poll-callback path calls
`progress.update_item(task_id, sn_pct)` ONLY (not the
ProgressCallback). When progress is None, the existing
ProgressCallback path is preserved unchanged. (No
double-emission either way.)

AC11 (type strictness):
**Given** the refactor
**When** pyright strict + mypy strict run
**Then** 0 errors. No `# type: ignore`. Signatures use
`BatchProgressProtocol | None` directly.

## Must NOT

* Must NOT change the existing positional argument order of
  `upgrade` or `batch_upgrade`. `progress` is keyword-only.
* Must NOT remove the existing `console` parameter or the
  existing `ProgressCallback`. Both stay for non-progress
  callers.
* Must NOT call `progress.console.print` AND `console.print`
  for the same event -- choose one based on whether progress is
  provided.
* Must NOT swallow exceptions raised by `progress.start_item /
  update_item / finish_item`. If the progress display crashes,
  the caller wants to know.

## Tasks / Subtasks

* [ ] Grep for all call sites of `PluginExecutor.upgrade` and
      `PluginExecutor.batch_upgrade`:
      `grep -rn "\.upgrade(\|\.batch_upgrade(" src/ tests/`
* [ ] Edit `src/nexus/plugins/executor.py`:
  * [ ] Add `progress: BatchProgressProtocol | None = None`
        keyword-only param to `upgrade()`
  * [ ] Add same kwarg to `batch_upgrade()`
  * [ ] Inside `upgrade`: if progress is provided, call
        `start_item`, set up poll callback to call
        `update_item`, call `finish_item` at end with measured
        duration
  * [ ] Inside `batch_upgrade`: if progress is provided, call
        `start_batch(len(targets))` once, then the per-item
        sequence. Route `_console.print` calls through
        `progress.console.print`
* [ ] Update existing call sites if any pass `progress=` (none
      should yet) -- expected: zero changes needed at this story
* [ ] Create `tests/test_executor_upgrade_with_progress.py`:
  * [ ] `test_upgrade_with_progress_none_preserves_existing_behavior`
  * [ ] `test_upgrade_with_progress_records_start_update_finish`
  * [ ] `test_upgrade_with_progress_finish_success_when_completed`
  * [ ] `test_upgrade_with_progress_finish_failure_when_failed`
* [ ] Create `tests/test_executor_batch_upgrade_with_progress.py`:
  * [ ] `test_batch_upgrade_with_progress_calls_start_batch_once`
  * [ ] `test_batch_upgrade_with_progress_routes_output_through_bp_console`
  * [ ] `test_batch_upgrade_with_progress_skip_on_fail_records_failure_then_continues`
  * [ ] `test_batch_upgrade_with_progress_none_preserves_existing_behavior`
* [ ] Update `.ratchet.json` if executor coverage changes

## Existing Code

* `src/nexus/plugins/executor.py` -- `upgrade()`, `batch_upgrade()`,
  `_console` field, existing `ProgressCallback`
* `src/nexus/plugins/progress.py:ProgressPoller` -- poll callback
  receives `ProgressState` with `percent_complete: int`
* `tests/fakes/batch_progress.py:FakeBatchProgress` (Story 03)

## Dev Notes

### Routing decision tree

```python
def upgrade(self, plugin_id, *, progress=None, console=None):
    out = console or self._console
    target_console = progress.console if progress else out
    ...
    if progress:
        item_id = progress.start_item(plugin_id, family)
    def on_progress(state):
        if progress:
            progress.update_item(item_id, state.percent_complete)
        # existing ProgressCallback path stays for non-progress
        # callers
    ...
    if progress:
        progress.finish_item(item_id, duration_s, family, success)
```

### Grep audit before editing

The existing executor likely calls `self._console.print("upgrading
%s", ...)` and similar in multiple places. Each such call must be
checked: when progress is provided, route through
`target_console` (which is `progress.console`); when not, route
through `out` (which is `console or self._console`).

### Conventions

* Absolute imports
* No `# type: ignore`
* Coverage stays at 100%; ratchet updated if line count changes

## References

* PRD: `.primer/prd/PRD-001-cli-ux-wow-factor.md` (Refactoring
  section)
* Original story:
  `.primer/stories/2026.05.02-cli-batch-progress-eta.md` (Task 4
  + Task 13)
* Brainstorming: `.primer/brainstorming/2026-05-18-cli-ux-implementation-plan.md`
