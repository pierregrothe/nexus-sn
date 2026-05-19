# Story 03: BatchProgressProtocol + Rich/PlainBatchProgress + factory

Status: ready
Spec-Clarity: high
Depends-On: 02

## Story

As a NEXUS user running a batch upgrade,
I want the progress display to adapt to my terminal --
a Live region with brand bars on RICH/BASIC, plain status lines
on LEGACY/PLAIN --
so that I get usable feedback whether I'm at a modern terminal or
piping output to a CI log.

## Acceptance Criteria

AC1 (protocol surface):
**Given** a consumer wants to drive a batch progress display
**When** the consumer imports `BatchProgressProtocol`
**Then** the protocol declares: `start_batch(total: int) ->
int` (returns task_id), `start_item(plugin_id: str, family: str)
-> int`, `update_item(task_id: int, sn_pct: int) -> None`,
`finish_item(task_id: int, duration_s: float, family: str,
success: bool) -> None`, `console` property returning `Console`,
and `__enter__ / __exit__` for context-manager use.

AC2 (RichBatchProgress wraps Rich Progress):
**Given** a RICH profile RenderContext
**When** `make_batch_progress(ctx, total=5)` is called
**Then** the return value is a `RichBatchProgress` instance.
Internally wraps a `rich.progress.Progress(...,
console=ctx.console)` with columns: SpinnerColumn (RICH only,
omitted on BASIC), TextColumn (description), BarColumn,
TaskProgressColumn, TimeElapsedColumn, WeightedETAColumn.

AC3 (RichBatchProgress overall + transient per-item):
**Given** a RichBatchProgress in context
**When** `start_batch(5)` then `start_item("plugin.a", "family-x")`
then `update_item(item_id, 50)` then `finish_item(item_id, 30.0,
"family-x", success=True)`
**Then** the overall task advances by 1; the per-item task was
created with `transient=True` and is removed on finish_item.

AC4 (RichBatchProgress writes EmaPriorStore on finish):
**Given** a RichBatchProgress wrapping an `EmaPriorStore`
**When** `finish_item(task_id, duration_s=42.0, family="X",
success=True)` is called
**Then** `store.record("X", 42.0)` is invoked. (When success is
False, NO record is made -- failed-upgrade durations would
contaminate priors.)

AC5 (RichBatchProgress reads EmaPriorStore on start_item):
**Given** a RichBatchProgress on a family with prior records
**When** `start_item("p", "X")` is called
**Then** the per-item task is created with
`fields={"sn_pct": 0, "ema_duration_s": ema_compute(samples)}`
where samples is `store.load("X")`. WeightedETAColumn reads
these on render.

AC6 (PlainBatchProgress prints one line per event):
**Given** a LEGACY or PLAIN profile RenderContext
**When** `make_batch_progress(ctx, total=2)` returns
`PlainBatchProgress`
**Then** sequential calls
`start_batch(2)` -- no output (or "batch started 2 items" line)
`start_item("p", "X")` -- prints `upgrading p`
`update_item(item_id, 50)` -- prints `upgrading p 50%`
`finish_item(item_id, 12.0, "X", success=True)` -- prints
`upgraded p 00:12`
`finish_item(item_id, 12.0, "X", success=False)` -- prints
`failed p 00:12`

AC7 (PlainBatchProgress no carriage return):
**Given** any sequence of calls on PlainBatchProgress
**When** the recorded output is inspected
**Then** no `\r` characters are present in the output.

AC8 (factory dispatch):
**Given** four RenderContexts with profiles RICH / BASIC /
LEGACY / PLAIN
**When** `make_batch_progress(ctx, total=1)` is called for each
**Then** RICH -> `RichBatchProgress`, BASIC ->
`RichBatchProgress` (no spinner column), LEGACY ->
`PlainBatchProgress`, PLAIN -> `PlainBatchProgress`.

AC9 (factory dispatch -- both impls satisfy protocol):
**Given** the four results from AC8
**When** each is type-checked against `BatchProgressProtocol`
**Then** `isinstance(bp, BatchProgressProtocol)` is True for all
four. (Protocol is `@runtime_checkable`.)

AC10 (context manager safe):
**Given** any `BatchProgressProtocol` impl
**When** `with make_batch_progress(...) as bp: raise ValueError`
**Then** the exception propagates, the Live region (if any) is
cleanly torn down, and no orphan threads or terminal-state
corruption results.

AC11 (FakeBatchProgress in tests/fakes/):
**Given** the test surface needs a recording impl
**When** Story 03 ships
**Then** `tests/fakes/batch_progress.py` exposes a
`FakeBatchProgress(BaseModel)` that records all method calls into
`recorded_calls: tuple[tuple[str, dict[str, object]], ...]` and
exposes a `console` property pointing to
`Console(file=StringIO())`.

## Must NOT

* Must NOT use `\r` carriage-return rewrites in
  `PlainBatchProgress`. One full line per event.
* Must NOT call `console.print(...)` directly for output that
  should interleave with the Live region. RichBatchProgress
  exposes `self.console` (the Progress's console) so callers
  route through it.
* Must NOT record failed-upgrade durations into `EmaPriorStore`.
* Must NOT depend on `tqdm` or any progress library other than
  Rich.
* Must NOT add a global / module-level `Progress` singleton. Each
  call to `make_batch_progress` returns a fresh instance.

## Tasks / Subtasks

* [ ] Create `src/nexus/ui/components/batch_progress.py`:
  * [ ] File header
  * [ ] `class BatchProgressProtocol(Protocol)` with
        `@runtime_checkable`
  * [ ] `class RichBatchProgress(BaseModel)` frozen + strict +
        extra="forbid" -- wraps `rich.progress.Progress`. Stores
        `_progress`, `_overall_task_id`, `store: EmaPriorStore`.
        `__enter__` starts the Progress's Live region;
        `__exit__` stops it. Implements all protocol methods.
  * [ ] `class PlainBatchProgress(BaseModel)` frozen + strict +
        extra="forbid" -- holds `console`, `total`. Prints one
        line per event. `__enter__` / `__exit__` are no-ops
        (idempotent context-manager surface).
  * [ ] `def make_batch_progress(ctx: RenderContext, total: int,
        store: EmaPriorStore | None = None) ->
        BatchProgressProtocol` factory
  * [ ] `__all__`
* [ ] Create `tests/fakes/batch_progress.py`:
  * [ ] `FakeBatchProgress(BaseModel)` recording impl
  * [ ] `recorded_calls: tuple[tuple[str, dict[str, object]],
        ...]` (mutable via frozen-list trick or non-frozen field)
* [ ] Create `tests/test_batch_progress_rich.py`:
  * [ ] `test_richbatchprogress_start_item_creates_transient_task`
  * [ ] `test_richbatchprogress_finish_item_records_to_store_on_success`
  * [ ] `test_richbatchprogress_finish_item_skips_store_on_failure`
  * [ ] `test_richbatchprogress_start_item_seeds_ema_from_store`
  * [ ] `test_richbatchprogress_console_property_returns_progress_console`
* [ ] Create `tests/test_batch_progress_plain.py`:
  * [ ] `test_plainbatchprogress_start_item_emits_upgrading_line`
  * [ ] `test_plainbatchprogress_update_item_emits_percent_line`
  * [ ] `test_plainbatchprogress_finish_item_success_emits_upgraded_line`
  * [ ] `test_plainbatchprogress_finish_item_failure_emits_failed_line`
  * [ ] `test_plainbatchprogress_output_contains_no_carriage_return`
* [ ] Create `tests/test_make_batch_progress.py`:
  * [ ] `test_make_batch_progress_returns_rich_for_rich_profile`
  * [ ] `test_make_batch_progress_returns_rich_for_basic_profile`
  * [ ] `test_make_batch_progress_returns_plain_for_legacy_profile`
  * [ ] `test_make_batch_progress_returns_plain_for_plain_profile`
  * [ ] `test_make_batch_progress_results_satisfy_protocol_runtime_check`
* [ ] Update `.ratchet.json` baseline
* [ ] Update `src/nexus/ui/components/__init__.py` re-exports

## Existing Code

* `nexus.ui.render_context.RenderContext` -- factory input
* `nexus.ui.capabilities.RenderProfile` -- dispatch key
* `nexus.ui.components.eta.WeightedETAColumn` (Story 02) -- column
* `nexus.ui.components.eta.ema_compute` (Story 02) -- prior
  computation
* `nexus.ui.components.eta_store.EmaPriorStore` (Story 01) --
  persistence

## Dev Notes

### Pydantic + Rich Progress

Rich's `Progress` is not a Pydantic-compatible type. Store it as a
private field with `Field(exclude=True)` or use a sibling
`@dataclass(slots=True)` wrapper. Alternative: skip Pydantic for
the Rich/Plain implementations and use `@dataclass(frozen=True,
slots=True)` -- the Protocol satisfaction is structural, not
nominal. Pick whichever passes pyright strict cleanly.

### RichBatchProgress columns

```python
Progress(
    SpinnerColumn() if ctx.profile is RenderProfile.RICH else "",
    TextColumn("[bold blue]{task.fields[plugin_id]}"),
    BarColumn(),
    TaskProgressColumn(),
    TimeElapsedColumn(),
    WeightedETAColumn(),
    console=ctx.console,
    transient=False,
)
```

The per-item task uses `transient=True`; the overall task uses
`transient=False`.

### FakeBatchProgress mutability

Pydantic frozen models with mutable list fields are tricky. Two
patterns work:
1. `recorded_calls: list[tuple[str, dict[str, object]]]` with
   `model_config = ConfigDict(frozen=False, ...)` -- breaks the
   frozen convention but is the simplest.
2. Use `@dataclass(slots=True)` for the fake (not Pydantic) --
   then mutability is natural. Recommended.

## References

* PRD: `.primer/prd/PRD-001-cli-ux-wow-factor.md`
  (BatchProgressProtocol section)
* Original story:
  `.primer/stories/2026.05.02-cli-batch-progress-eta.md`
  (Task 2 + Tasks 10-12)
* Brainstorming pivot: `.primer/brainstorming/2026-05-18-cli-ux-implementation-plan.md`
