# Epic: nexus CLI batch progress + ETA (v1)

Phase: 2026.05-setup-sync
Status: ready

## Goal

Deliver the batch-progress + ETA half of PRD-001: `nexus plugins
upgrade <id>` and `nexus plugins upgrade --family X` get a Rich
progress bar with WeightedETA on RICH/BASIC profiles and a
line-per-event status stream on LEGACY/PLAIN profiles. Along the
way, delete the dead pypager + PagedTable code that v1 of the PRD
proposed but `FramedViewer` superseded on day one.

## Source

* PRD: `../../prd/PRD-001-cli-ux-wow-factor.md` (v2 revision
  2026-05-18 records the pivot from pypager to FramedViewer)
* Brainstorming pivot:
  `../../brainstorming/2026-05-18-cli-ux-implementation-plan.md`
* Original brainstorm: `../../brainstorming/2026-05-15-cli-ux-wow-factor.md`
* Superseded story: `../../stories/2026.05.01-cli-paged-list-widget.md`
  (its substrate work landed; its consumer-wiring task is moot)
* Original batch-progress story:
  `../../stories/2026.05.02-cli-batch-progress-eta.md` (decomposed
  here into 5 sub-stories)

## Requirements Inventory

### Functional Requirements

* FR0 (dead-code deletion): pypager + PagedTable + PagerProtocol +
  PypagerPager are removed from the codebase and ratchet baselines.
  An ADR records the architectural reversal.
* FR1 (EmaPriorStore basic record): a JSON line
  `{"family": "...", "duration_s": F, "ts": ISO-UTC}` is appended
  to `~/.nexus/cache/eta_prior.jsonl` on every `record()` call.
* FR2 (EmaPriorStore mkdir guard): first `record()` call on a
  fresh install creates `~/.nexus/cache/` if absent.
* FR3 (EmaPriorStore load + filter + cap): `load(family)` reads
  the file, filters by family, returns up to 1000 most-recent
  durations. Malformed JSONL lines are skipped silently.
* FR4 (EmaPriorStore in-process safety): two threads writing 50
  lines each preserve all 100 records. (Cross-process safety
  declared out of scope; see Constraints.)
* FR5 (ema_compute pure): `ema_compute(samples, alpha=0.4) ->
  float` is a pure function. Empty -> 0.0. Single sample -> sample.
* FR6 (WeightedETAColumn estimating): renders "ETA: estimating..."
  when EMA samples list is empty.
* FR7 (WeightedETAColumn MM:SS): renders "ETA: MM:SS" when EMA
  samples list is non-empty, computed as
  `remaining_full_items * ema + (1 - sn_pct) * ema`.
* FR8 (BatchProgressProtocol surface): protocol declares
  `start_batch(total) -> int`, `start_item(plugin_id, family) ->
  int`, `update_item(task_id, sn_pct)`, `finish_item(task_id,
  duration_s, family, success)`, and `console` property + context
  manager methods.
* FR9 (RichBatchProgress wraps Live): RICH/BASIC factory return.
  Brand spinner (RICH only), WeightedETAColumn. Transient
  per-item tasks. `console.print` interleaves with the Live region.
* FR10 (PlainBatchProgress prints lines): LEGACY/PLAIN factory
  return. One line per event via `self.console.print`. No `\r`,
  no Live region.
* FR11 (make_batch_progress factory): dispatches on `ctx.profile`.
  RICH/BASIC -> RichBatchProgress; LEGACY/PLAIN ->
  PlainBatchProgress.
* FR12 (executor progress kwarg): `PluginExecutor.upgrade` and
  `PluginExecutor.batch_upgrade` accept
  `progress: BatchProgressProtocol | None = None` keyword-only.
  When None, behavior preserved exactly.
* FR13 (executor progress routing): when progress is provided,
  output that today goes to `console.print` flips to
  `progress.console.print`; SN-poll callbacks call
  `progress.update_item(task_id, sn_pct)`; per-item completion
  calls `progress.finish_item(...)` with duration_s and family.
* FR14 (CLI wire single-item): `nexus plugins upgrade <id>` opens
  `with make_batch_progress(ctx, total=1) as bp` and passes
  `progress=bp` to `executor.upgrade`.
* FR15 (CLI wire batch): `nexus plugins upgrade --family X` and
  `--all` open `with make_batch_progress(ctx, total=len(targets))
  as bp` and pass `progress=bp` to `executor.batch_upgrade`.
* FR16 (InteractiveRequiredError exit-2): `nexus plugins upgrade
  --family X` (or `--all`) without `--yes` on PLAIN profile raises
  `InteractiveRequiredError`, exit code 2.

### Non-Functional Requirements

* NFR1: 0 errors mypy strict + pyright strict. [CLAUDE.md]
* NFR2: No `unittest.mock` / `MagicMock`. Tests use real fakes +
  threading + tempfile. [no-mocks.md]
* NFR3: Python 3.14 syntax. [python-314.md]
* NFR4: Pydantic models stay `frozen=True, strict=True,
  extra="forbid"`. [CLAUDE.md]
* NFR5: ASCII only. File headers + Google docstrings + `__all__`.
* NFR6: File-size cap 800 src / 1400 tests. [ADR-023]
* NFR7: `ts` field on `EmaSample` is `UtcDatetime` (UTC enforced
  project-wide). [utc-timezone.md]
* NFR8: 100% line coverage on every new module; ratchet updated.

### Constraints

* C1: Single user-facing flag remains `--plain`. No new CLI flags
  added by this epic. [PRD-001]
* C2: Cross-process atomicity of `EmaPriorStore` is OUT of scope
  for v1. Two concurrent `nexus plugins upgrade --family X`
  invocations on Windows MAY interleave JSONL lines. Documented in
  `EmaPriorStore` docstring + PRD-001 Out-of-Scope.
* C3: `InteractiveRequiredError` exit code is 2 (typer
  convention), NOT 3. (Original story spec said 3 -- v2 corrects.)
* C4: No new runtime deps. Textual is already pinned. `pypager` is
  REMOVED in Story 00.
* C5: Story 00 deletes ratchet baselines for the removed modules
  -- not a coverage regression, since the modules themselves are
  gone.

## Stories

| #  | Title                                                                 | Clarity | Depends-On | Status  |
|----|-----------------------------------------------------------------------|---------|------------|---------|
| 00 | Delete dead paging code + ADR-XXX (Textual supersedes pypager)        | high    | none       | ready   |
| 01 | `EmaPriorStore` + `EmaSample` (JSONL, in-process multi-thread safe)   | high    | none       | ready   |
| 02 | `WeightedETAColumn` + `ema_compute` pure function                     | high    | 01         | ready   |
| 03 | `BatchProgressProtocol` + `Rich/PlainBatchProgress` + factory         | high    | 02         | ready   |
| 04 | `PluginExecutor.upgrade` + `batch_upgrade` progress kwarg refactor    | high    | 03         | ready   |
| 05 | Wire CLI commands + `InteractiveRequiredError` exit-2 + ADR finalize  | high    | 04         | ready   |

Story 00 is parallel-safe with 01. Stories 02..05 ship serially.

## Coverage Map

* FR0 -> 00
* FR1, FR2, FR3, FR4 -> 01
* FR5, FR6, FR7 -> 02
* FR8, FR9, FR10, FR11 -> 03
* FR12, FR13 -> 04
* FR14, FR15, FR16 -> 05
* NFR1..8 -> all stories
* C1..C5 -> all stories (gates per story)

## Existing Code Reused (delta-only)

* `src/nexus/ui/render_context.py:RenderContext` -- consumed by
  Story 03's factory.
* `src/nexus/cli/console.py:render_context` -- the singleton.
* `src/nexus/plugins/executor.py` -- Story 04 adds `progress`
  kwarg to `upgrade` + `batch_upgrade`.
* `src/nexus/plugins/progress.py:ProgressState.percent_complete` --
  Story 04 reads on each poll callback.
* `src/nexus/config/paths.py` -- Story 01 adds
  `eta_prior_cache_path() -> Path` helper.
* `src/nexus/cli/commands_plugins_exec.py` -- Story 05 wires
  `make_batch_progress` into `plugins_upgrade`.
* `src/nexus/cli/commands_plugins_outdated.py` -- Story 05 wires
  the family / all branches.
* `tests/conftest.py` -- existing console-capture fixture
  (`Console(force_terminal=..., file=StringIO())`) reused.

## Progress

* Stories: 0/6 done, 6 ready

## Dead-Code Inventory (Story 00 target)

Files to delete:

* `src/nexus/ui/components/paged_table.py`
* `src/nexus/ui/components/pager.py`
* `tests/test_paged_table*.py` (whichever exist)
* `tests/test_pager*.py` (whichever exist)

Exports to remove from `src/nexus/ui/components/__init__.py`:

* `PagedTable`
* `PagerProtocol`
* `PypagerPager`

Ratchet baselines to remove from `.ratchet.json`:

* `nexus.ui.components.paged_table`
* `nexus.ui.components.pager`

Dependency to remove from `pyproject.toml`:

* `pypager = "^3.0.1"`

Re-run `poetry lock` after dep removal. Update `poetry.lock`.

ADR to draft in Story 00 (finalize in Story 05):

* `.primer/adr/ADR-XXX-framedviewer-supersedes-pypager.md`
  (numbered when written -- next free ADR slot).
