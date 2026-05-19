# Story 02: WeightedETAColumn + ema_compute pure function

Status: done
Spec-Clarity: high
Depends-On: 01

## Story

As a NEXUS user watching a multi-item plugin upgrade,
I want the progress display to show a useful ETA that adapts
based on how long similar upgrades have taken before,
so that I know whether to grab coffee or stay at my keyboard.

## Acceptance Criteria

AC1 (ema_compute is pure):
**Given** the math helper exists
**When** `ema_compute(samples, alpha)` is called with the same
inputs twice
**Then** the return value is identical; no side effects; no I/O.

AC2 (ema_compute empty list):
**Given** an empty list `()`
**When** `ema_compute((), alpha=0.4)` runs
**Then** the return value is `0.0`.

AC3 (ema_compute single sample):
**Given** `(7.5,)`
**When** `ema_compute((7.5,), alpha=0.4)` runs
**Then** the return value is exactly `7.5`.

AC4 (ema_compute biases recent):
**Given** `(1.0, 100.0)` (most-recent sample is 100.0)
**When** `ema_compute((1.0, 100.0), alpha=0.4)` runs
**Then** the result is between 50 and 100 (recent dominates),
specifically `0.6 * 1.0 + 0.4 * 100.0 = 40.6` if we treat index
0 as the prior accumulator... NO -- the canonical recursive form
is `ema = alpha * x + (1 - alpha) * prev`. With prev seeded to
first sample: `ema(1.0) -> 1.0; ema(100.0) -> 0.4*100 + 0.6*1 =
40.6`. Test asserts `== 40.6` exactly (float comparison via
`pytest.approx`).

AC5 (ema_compute many samples):
**Given** `(10.0, 10.0, 10.0, 10.0)` (homogeneous)
**When** `ema_compute(...)` runs
**Then** the result is `10.0` (converges to the constant).

AC6 (WeightedETAColumn estimating mode):
**Given** a `rich.progress.Task` with `fields = {"sn_pct": 0,
"ema_duration_s": 0.0}` (no prior samples)
**When** `WeightedETAColumn().render(task)` runs
**Then** the returned `rich.text.Text` equals `"ETA: estimating..."`.

AC7 (WeightedETAColumn MM:SS):
**Given** a `Task` with `total=3, completed=1, fields={"sn_pct":
50, "ema_duration_s": 60.0}` (one item done, half through item 2,
60-second EMA)
**When** `render(task)` runs
**Then** the column shows `"ETA: 02:30"` -- 60 sec to finish the
current item + 1 full remaining item at 60 sec + adjustment.
Formula: `remaining_full_items * ema + (1 - sn_pct/100) * ema =
1 * 60 + (1 - 0.5) * 60 = 90 sec`. (Test asserts `"ETA: 01:30"`.)

(Wait -- AC7 formula needs revisiting. Re-derive:
`remaining_full = total - completed - 1 = 3 - 1 - 1 = 1` (the
items after the current in-flight one).
`current_remaining_frac = 1 - sn_pct/100 = 0.5`.
ETA = `(remaining_full * ema) + (current_remaining_frac * ema)`
= `(1 * 60) + (0.5 * 60)` = 90 sec = `01:30`.
AC7 expects `"ETA: 01:30"`.)

AC8 (WeightedETAColumn format MM:SS over 60 minutes):
**Given** `total=10, completed=0, fields={"sn_pct": 0,
"ema_duration_s": 720.0}` (12-min items, 10 to go)
**When** `render(task)` runs
**Then** the column shows `"ETA: 120:00"` (12 * 10 = 120 min).
Format does NOT roll into HH:MM:SS; stays MM:SS even at high
counts.

AC9 (WeightedETAColumn returns rich.text.Text):
**Given** a render call
**When** the return value is inspected
**Then** it is `rich.text.Text` instance (not str). Style is
`"dim"` for estimating mode and `None` for MM:SS mode.

AC10 (no type ignore, ASCII):
**Given** the new file
**When** pyright strict + mypy strict run
**Then** 0 errors. ASCII only.

## Must NOT

* Must NOT depend on `EmaPriorStore` directly. The column reads
  `task.fields["ema_duration_s"]` -- caller computes this from
  the store. Keeps the column pure.
* Must NOT use HH:MM:SS format. MM:SS is the project convention
  per PRD-001.
* Must NOT raise on missing task fields. Treat missing as zero;
  triggers the estimating-mode path.

## Tasks / Subtasks

* [ ] Create `src/nexus/ui/components/eta.py`:
  * [ ] File header
  * [ ] `def ema_compute(samples: tuple[float, ...], alpha:
        float = 0.4) -> float` -- pure
  * [ ] `class WeightedETAColumn(rich.progress.ProgressColumn)`
    * [ ] Override `render(self, task: rich.progress.Task) ->
          rich.text.Text`
    * [ ] Read `task.fields.get("sn_pct", 0)` and
          `task.fields.get("ema_duration_s", 0.0)`
    * [ ] If `ema_duration_s == 0.0`: return `Text("ETA:
          estimating...", style="dim")`
    * [ ] Else compute ETA via formula, return
          `Text(f"ETA: {mm:02d}:{ss:02d}")`
  * [ ] `__all__ = ["WeightedETAColumn", "ema_compute"]`
* [ ] Create `tests/test_ema_compute.py`:
  * [ ] `test_ema_compute_with_empty_samples_returns_zero`
  * [ ] `test_ema_compute_with_one_sample_returns_sample`
  * [ ] `test_ema_compute_with_two_samples_biases_recent`
  * [ ] `test_ema_compute_with_homogeneous_samples_converges`
* [ ] Create `tests/test_weighted_eta_column.py`:
  * [ ] `test_render_with_no_samples_returns_estimating_text`
  * [ ] `test_render_with_samples_returns_mm_ss_text`
  * [ ] `test_render_with_long_eta_uses_mm_ss_not_hh_mm_ss`
  * [ ] `test_render_with_partial_item_blends_sn_pct`
  * [ ] `test_render_returns_rich_text_instance_not_str`
* [ ] Update `.ratchet.json` baseline
* [ ] Update `src/nexus/ui/components/__init__.py` re-exports

## Existing Code

* `rich.progress.ProgressColumn` -- subclass
* `rich.text.Text` -- return type
* `tests/conftest.py` -- no new fixtures needed; hand-build
  `rich.progress.Task` in tests

## Dev Notes

### Hand-built Task for tests

```python
from rich.progress import Task, TaskID
task = Task(
    id=TaskID(0),
    description="test",
    total=3,
    completed=1,
    fields={"sn_pct": 50, "ema_duration_s": 60.0},
    _get_time=lambda: 0.0,
    _tasks=...,  # may need a Progress instance; check Rich's API
)
```

If Task construction is too invasive, the column can be tested
by spinning up a real `Progress(transient=True, console=Console(
file=StringIO()))` with our column, adding a task with the
expected fields, and inspecting the render output.

### EMA recursive form

```python
def ema_compute(samples, alpha=0.4):
    if not samples:
        return 0.0
    prev = samples[0]
    for s in samples[1:]:
        prev = alpha * s + (1 - alpha) * prev
    return prev
```

### Conventions

* Absolute imports
* 100% coverage
* Pure functions where possible (ema_compute is pure)

## References

* PRD: `.primer/prd/PRD-001-cli-ux-wow-factor.md`
  (WeightedETAColumn section)
* Original story:
  `.primer/stories/2026.05.02-cli-batch-progress-eta.md` (Task 1,
  Task 9)
* Brainstorming: `.primer/brainstorming/2026-05-18-cli-ux-implementation-plan.md`
