# Brainstorming: CLI UX implementation plan (post-pivot)

Date: 2026-05-18
Mode: assumptions (research-driven gap analysis + adversarial pivot)
Techniques: assumptions-mode + adversarial-review (the review FORCED a
pivot -- this artifact is the v2 plan)

Trigger: Roadmap shows two CLI-UX items open in the 2026.05 phase. A
gap-analysis brainstorm was started; the adversarial review surfaced
that PRD-001's "no Textual" fence had already been silently broken
on main. This v2 artifact records the pivot.

## Context Brief

### PRD-vs-code divergence (the pivot trigger)

PRD-001 (`.primer/prd/PRD-001-cli-ux-wow-factor.md`) was written
2026-05-15 and committed in `8528230` (May 16). Its Out-of-Scope fence
declared: "We will NOT add Textual as a dependency. The TUI app
paradigm is wrong for one-shot CLI commands."

The same commit (`8528230`) introduced:

* `textual = "^8.2.6"` in `pyproject.toml:26`
* `src/nexus/ui/components/framed_viewer.py` -- a full Textual App
  with sticky frame, virtual scroll, `/` filter, sort, clipboard
  copy, modal details
* `_emit_framed_view` in `cli/views.py` -- dispatches `nexus plugins
  list` and `nexus plugins outdated` to FramedViewer on RICH/BASIC
* `_emit_inline_view` -- LEGACY/PLAIN fallback using raw `DataTable`

In parallel, the same commit also added `pypager ^3.0.1`,
`PagedTable`, and `PypagerPager` -- but `PagedTable` has **zero
consumers** in the codebase. Dead code that locked itself into the
ratchet at 100% coverage.

So PRD-001's stated architecture and the implementation diverged at
the moment of authoring. The divergence was never recorded in
`decisions.md`, any ADR, or `governance.md`.

### Current code state (canonical paths)

* `nexus plugins list` -- `_emit_framed_view` -> FramedViewer (Textual)
  on RICH/BASIC; `_emit_inline_view` -> raw `DataTable` on LEGACY/PLAIN
  and on FramedViewer crash
* `nexus plugins outdated` -- same `_emit_framed_view` path
* `nexus plugins upgrade <id>` and `nexus plugins upgrade --family`
  -- no progress reporting at all (just status prints)
* `nexus status` -- Terminal panel renders profile + caps via
  `_terminal_panel`

### What this means for the brainstorm scope

* Story 01 (paged-list-widget) is superseded: FramedViewer is the
  RICH/BASIC paging path and is already shipped. PagedTable is dead
  code to delete.
* Story 02 (batch-progress-eta) is unchanged: greenfield, all
  modules absent, the use case (long batch upgrades with no
  feedback) is real and the design in the story spec still applies.
* PRD-001 needs a rewrite to record reality.

## Key Insights

1. **The PRD broke its own anti-creep fence on day one.** Textual
   was banned in Out-of-Scope; the same commit added Textual. This
   was never adjudicated -- no ADR records the deviation. Lesson:
   the brainstorm/PRD/code chain needs a reconciliation step
   whenever code lands in the same commit as the PRD.

2. **FramedViewer is the right answer for list-paging.** Sticky
   frame, virtual scroll, in-pane filter and sort are the "wow
   factor" the PRD chased. Reverting to pypager + PagedTable would
   delete working UX to satisfy a stale fence.

3. **PagedTable + pypager + PagerProtocol + PypagerPager are dead
   code.** Removed dependency `pypager` saves ~5 KB but the real
   win is removing parallel paging implementations that diverge
   over time.

4. **Story 02's batch-progress stack is untouched by the pivot.**
   `BatchProgressProtocol`, `WeightedETAColumn`, `EmaPriorStore`,
   `RichBatchProgress`, `PlainBatchProgress` -- none of these
   overlap with FramedViewer. The Story 02 spec still applies.

5. **Adversarial review caught real issues beyond the pivot.**
   Multi-writer atomicity of `EmaPriorStore` on Windows is NOT
   guaranteed by `open(mode='a')` (POSIX O_APPEND semantics differ
   from Windows `WriteFile`). The two-thread test in Story 02 spec
   does not exercise the cross-process case. Documented as a
   constraint in the new epic.

6. **`InteractiveRequiredError` exit-3 is unanchored.** Project has
   no exit-code registry. Need to either (a) document codes 0/1/3
   in patterns.md or (b) pick a different code that doesn't shadow
   POSIX `diff` (which uses 3 for "trouble"). Choosing exit-2
   (typer's default for usage errors) keeps within typer convention
   without shadowing.

## Recommendations (v2)

1. **Update PRD-001 in place.** Remove the Textual ban; add Textual
   as accepted (cite FramedViewer reality); declare pypager /
   PagedTable / PagerProtocol / PypagerPager OUT-of-scope (to be
   deleted). Keep batch-progress / ETA / EmaPriorStore /
   InteractiveRequired sections as-is.

2. **Single epic at `.primer/epics/2026.05-cli-ux-batch-progress/`.**
   6 stories: 1 dead-code deletion + 5 greenfield batch-progress
   modules. Phase-A wiring of list commands is REMOVED -- there is
   no wiring to do; FramedViewer is already wired.

3. **Use `typer.Exit(2)` for InteractiveRequiredError, not 3.** 2
   is typer's convention for usage errors. Avoids POSIX `diff`
   shadowing.

4. **Document Windows append-atomicity constraint.** Story 01
   (ema_prior_store) MUST include an `Os.write(fd, line, ...)` path
   using `os.O_APPEND | os.O_WRONLY` AND a Windows-specific note in
   the docstring. Multi-process safety on Windows requires a
   `msvcrt.locking` fallback. Story spec gets the constraint
   recorded; cross-process test can be added as a Must NOT (we do
   not claim cross-process atomicity in v1).

5. **Draft an ADR titled "FramedViewer (Textual) supersedes pypager
   for sticky-frame paging."** Captures the architectural reversal
   for governance. Becomes part of Story 00 (dead-code deletion).

6. **Mark Story 2026.05.01 as superseded** with a one-line note
   pointing at FramedViewer + the new epic. Do not delete it --
   record-of-history matters.

## Trade-offs (v2)

| Option | Pro | Con | Position |
|---|---|---|---|
| Keep pypager + PagedTable as future fallback | Optionality | Dead code rots; ratchet locks 100% coverage on unused modules | Reject |
| Add Textual `App.run_inline()` for non-fullscreen | Less invasive UX | FramedViewer is already full-screen; mixing modes is a rabbit hole | Reject |
| Roll back FramedViewer entirely | Honors original PRD | Throws away working sticky-frame UX | Reject |
| `typer.Exit(3)` for InteractiveRequired | Matches story spec | Shadows POSIX `diff` exit | Reject |
| `typer.Exit(2)` for InteractiveRequired | Typer convention | Different from story spec | Adopt -- spec updated |
| `EmaPriorStore` cross-process locking via `msvcrt` | True multi-writer safety | Adds Windows-specific code path | Reject for v1 -- document constraint in docstring |

## Out of Scope (carry forward from PRD-001, with edits)

* Custom termios scroller (unchanged)
* `--pager / --no-pager / --limit / --no-color` flags (unchanged)
* Mid-command profile switching (unchanged)
* Per-family hard-coded ETA priors (unchanged)
* Migrating non-PRD-named commands to RenderContext (unchanged)
* Mouse / clickable rows (FramedViewer already supports keyboard;
  mouse remains out of scope)
* User-customizable color themes (unchanged)
* Profile-detection caching across invocations (unchanged)
* Async-streaming row updates (unchanged)
* Cross-process atomicity of `EmaPriorStore` (NEW -- documented
  constraint; v1 covers in-process multi-threaded only)
* pypager / PagedTable / PagerProtocol / PypagerPager (NEW --
  superseded by FramedViewer; deletion is Story 00 in the new
  epic)

## Proposed Story Breakdown (v2)

Epic dir: `.primer/epics/2026.05-cli-ux-batch-progress/`

| #  | Title                                                                 | Depends-On |
|----|-----------------------------------------------------------------------|------------|
| 00 | Delete pypager + PagedTable + Pager dead code, draft ADR              | none       |
| 01 | `EmaPriorStore` + `EmaSample` (JSONL, in-process multi-thread safe)   | none       |
| 02 | `WeightedETAColumn` + `ema_compute` pure function                     | 01         |
| 03 | `BatchProgressProtocol` + `Rich/PlainBatchProgress` + factory         | 02         |
| 04 | `PluginExecutor.upgrade` + `batch_upgrade` progress kwarg refactor    | 03         |
| 05 | Wire CLI commands + `InteractiveRequiredError` exit-2 + ADR finalize  | 04         |

Story 00 is independent. Stories 01-05 are a strict serial chain.

## Open Questions (resolved)

* Q1 (resolved): PagedTable consumer wiring -- moot, code is dead.
* Q2 (resolved): epic dir is `2026.05-cli-ux-batch-progress` (new
  name reflects post-pivot scope).
* Q3 (NEW, resolved): InteractiveRequiredError exit code is 2, not
  3, to match typer convention and avoid POSIX `diff` shadowing.

## Adversarial Review

### Adversarial round 1 (the pivot trigger)

The reviewer caught:

1. **Story 01 premise factually wrong** -- `nexus plugins list`
   already routes through FramedViewer, not raw DataTable.
2. **PagedTable has zero consumers** -- dead code at 100%
   coverage.
3. **PRD-001 contradicts current code** -- Textual is in
   `pyproject.toml` despite the PRD's anti-creep fence.
4. **Windows append-atomicity claim is wrong** -- POSIX `O_APPEND`
   semantics do not apply to `open('a')` on Windows.
5. **Exit-code 3 shadows POSIX `diff`** -- no project convention
   exists.
6. **`~/.nexus/cache/` mkdir guard missing** -- first
   `EmaPriorStore.record()` will `FileNotFoundError` on clean
   install.
7. **Stale line reference** -- `cli.py:1716` no longer exists;
   `cli.py` was split into `cli/` package in commit `8528230`.
8. **Story 02 sub-decomposition undefined** -- the public
   interfaces of stories 03..06 in v1 plan were not specified.
9. **`FakeBatchProgress` surface incomplete** -- `start_batch` and
   `console` property were missing from the recording spec.

### v2 resolutions

* (1)(2)(3): Pivoted to dead-code deletion + PRD rewrite (Story
  00).
* (4): Constraint documented; cross-process safety declared out of
  scope for v1.
* (5): Switched to exit-2 (typer convention).
* (6): Story 01 (ema_prior_store) must include a mkdir-or-exist
  guard before first write.
* (7): The new epic does not reference any line numbers; just
  module names.
* (8): Each story file in the new epic gets full task / AC
  breakdowns derived from the original Story 02 BMAD spec.
* (9): `FakeBatchProgress` records ALL protocol methods including
  `start_batch` and exposes a `Console(file=StringIO())` via the
  `console` property.

### Adversarial round 2

Not needed for this artifact. The v1 -> v2 pivot already resolved
all blocking gaps from round 1. Adversarial review can re-run after
the epic + story files land, if the user wants.

## Research Findings Appendix

### Substrate-already-shipped finding

`.ratchet.json` baselines confirm `nexus.ui.capabilities` (70/70),
`nexus.ui.components.paged_table` (48/48), `nexus.ui.components.pager`
(8/8), `nexus.ui.render_context` (13/13), `nexus.ui.components.framed_viewer`
(46/46) are all at 100%. The first three are dead-code targets; the
last is the canonical paging path.

### FramedViewer commit provenance

Commit `8528230` ("feat(cli): brew-style outdated/upgrade...")
authored 2026-05-16 Pierre Grothe added Textual + FramedViewer
together with PRD-001. The commit message does not mention Textual
or FramedViewer; it focuses on the outdated/upgrade split.

### PluginExecutor surface (unchanged from v1)

`src/nexus/plugins/executor.py` has `upgrade()` and `batch_upgrade()`;
both lack `progress` keyword-only param.
`src/nexus/plugins/progress.py:69` exposes `percent_complete: int`
on `ProgressState`. `ProgressCallback` is an existing extension
point.

### Windows append-atomicity

Python's `open(path, 'a')` on Windows opens the file with
`os.O_APPEND` but the underlying `WriteFile` call is NOT atomic
across processes unless `FILE_APPEND_DATA` access is requested
without `FILE_WRITE_DATA`. CPython does not request this; concurrent
`open('a')` writes from separate processes may interleave on
Windows. In-process multi-threaded writes are still safe because
the GIL serializes `os.write`. v1 of `EmaPriorStore` covers the
in-process case only.

### Exit code conventions

`diff` (POSIX): 0 same, 1 different, 2+ trouble. `grep`: 0 match,
1 no match, 2+ error. `pytest`: 0 pass, 1 fail, 2 interrupted, 3
internal error, 4 usage, 5 no tests collected. `typer`: 0 success,
1 user error/exception, 2 usage error (incl. missing required arg).
Adopting `typer.Exit(2)` for InteractiveRequiredError aligns with
typer convention.

## Session Notes

### Round 1: gap analysis (superseded by round 2)

Started from "brainstorm cli-ux items" user prompt. Researcher
returned substrate-already-shipped finding. Drafted a 6-story plan
on the assumption that PagedTable needed wiring.

### Round 2: adversarial pivot

Reviewer caught PRD-vs-code divergence and dead-code reality. User
confirmed pivot to "Update PRD + delete dead code". This v2
artifact replaces the v1 plan.
