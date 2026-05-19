---
id: PRD-001
title: CLI UX wow factor -- adaptive rendering + batch progress with ETA
status: draft
date: 2026-05-15
revised: 2026-05-18
adrs: []
charter_link: charter.md
milestone: 2026.05-setup-sync
---

# PRD-001: CLI UX wow factor -- adaptive rendering + batch progress with ETA

## Revision History

* 2026-05-15 -- v1 authored. Proposed pypager + PagedTable +
  TerminalCapabilities + RenderContext substrate, single `--plain`
  flag, BatchProgressProtocol with weighted ETA. Textual explicitly
  banned in Out-of-Scope.
* 2026-05-18 -- v2 reconciles with reality. Commit `8528230` (the
  same commit that introduced v1 of this PRD) silently added
  `textual = "^8.2.6"` and a full-screen FramedViewer App which is
  now the canonical paging path for `nexus plugins list` and
  `nexus plugins outdated`. pypager / PagedTable / PagerProtocol /
  PypagerPager were shipped but never consumed -- dead code. v2:
  (a) removes the Textual ban, (b) declares FramedViewer the
  canonical sticky-frame solution, (c) moves pypager + PagedTable
  + PagerProtocol + PypagerPager into Out-of-Scope as dead code
  scheduled for deletion, (d) keeps the batch-progress / ETA /
  EmaPriorStore / InteractiveRequiredError scope intact, (e) changes
  InteractiveRequiredError exit code from 3 to 2 to match typer
  convention. See `.primer/brainstorming/2026-05-18-cli-ux-implementation-plan.md`
  for the pivot trail.

## Problem

`nexus plugins list` USED TO dump 500+ rows in a single non-scrollable
table. Commit `8528230` shipped FramedViewer (Textual TUI with sticky
header, virtual scroll, `/` inline filter, sort, Enter for row
details, `r` refresh, `y` clipboard copy) which addresses the
list-paging problem already. **What remains unsolved**: long-running
operations -- `nexus plugins upgrade <id>` and `nexus plugins
upgrade --family <X>` (formerly `updates --apply`) -- still display
no progress feedback, no ETA, no batch-level "X of N complete."
Plugin upgrades observed in production range 30 s -- 15 min each;
batch operations feel like a black box.

## Users

* Human operators running NEXUS interactively in modern terminals
  (Windows Terminal, iTerm, gnome-terminal, kitty, VS Code).
* Human operators on legacy environments (pre-Windows-Terminal
  cmd.exe, tmux/screen multiplexers with limited ANSI support).
* CI pipelines invoking NEXUS in non-TTY mode (auto-degrade to plain
  text, line-per-event progress).
* Operators piping NEXUS output to grep / awk / further pipelines
  (force PLAIN profile via `--plain` flag).

## In Scope (must-haves)

### Capability detection (shipped, retained as-is)

* `TerminalCapabilities` frozen Pydantic model in
  `src/nexus/ui/capabilities.py`. Fields: is_tty, is_ci, color_depth,
  cols, rows, legacy_windows, term_program, is_dumb_terminal,
  is_multiplexer, no_color_env, forced_plain, supports_hyperlinks.
* `RenderProfile` StrEnum (RICH / BASIC / LEGACY / PLAIN) chosen by
  pure `pick_profile(caps)` function.
* `RenderContext` frozen `@dataclass(slots=True)` carrying
  `(console, caps, profile)`. Built once at process startup in
  `make_console()`, accessed via `get_render_context(ctx)`.

### Single entrypoint (shipped, retained as-is)

* ONE user-facing flag: `--plain`.
* Standard env-var conventions: `$NO_COLOR`, `$TERM=dumb`,
  `$NEXUS_PLAIN=1`.
* NO `--pager / --no-pager / --limit / --no-color` flags.

### nexus status Terminal panel (shipped, retained as-is)

* `nexus status` renders a "Terminal" panel showing the detected
  profile and inputs: `Profile: RICH | TTY: yes | CI: no | Color:
  TRUECOLOR | Size: 120x40 | Terminal: WindowsTerminal | Pager:
  framed`.

### Rendering components (REVISED in v2)

* **FramedViewer (canonical, shipped):** Textual App in
  `src/nexus/ui/components/framed_viewer.py`. Sticky header /
  footer, virtual-scroll body, `/` inline filter, sort, `r`
  refresh, `Enter` for row-detail modal, `y` clipboard. Used by
  `_emit_framed_view` on RICH/BASIC profiles.
* **Inline DataTable fallback (shipped):** `_emit_inline_view` in
  `cli/views.py` renders raw `DataTable` for LEGACY / PLAIN
  profiles and as fallback when FramedViewer cannot start.
* **BatchProgressProtocol (PENDING -- new epic):** Protocol with
  two implementations.
  * `RichBatchProgress` (RICH/BASIC): Rich `Progress` with overall
    task + transient per-item tasks, brand spinner,
    `WeightedETAColumn`.
  * `PlainBatchProgress` (LEGACY/PLAIN): one status line per event
    via `console.print` -- no Live region, no `\r`
    (multiplexer-safe).
  * Factory: `make_batch_progress(ctx, total) ->
    BatchProgressProtocol`.
* **WeightedETAColumn (PENDING):** blends SN-reported in-flight
  percent with EMA (alpha=0.4) of completed-item durations.
  Display "ETA: estimating..." until item 2 completes. No
  hard-coded family priors.
* **EmaPriorStore (PENDING):** append-only JSONL at
  `~/.nexus/cache/eta_prior.jsonl`. Records
  `{family, duration_s, ts}`. Capped at 1000 entries with
  truncate-oldest on read. **In-process multi-thread safe**;
  cross-process atomicity is out of scope for v1.
* **ASCII glyph palette (shipped):**
  `[ok] [!!] [..] [->] [*]` paired with theme styles. Color-graded
  `severity_color(score)` HSL hue 120->0. Middle-truncation helper
  for long plugin IDs.

### Refactoring (PENDING)

* `PluginExecutor.batch_upgrade` accepts injected
  `BatchProgressProtocol | None` (None preserves current behavior).
* `PluginExecutor.upgrade` (single-item path) accepts the same
  optional injection.
* `make_console()` performs an `_argv_has_plain()` pre-scan of
  `sys.argv` so the Console is built before Typer parses argv.
  (Shipped.)

### Interactive-required commands (PENDING -- exit code revised)

* Commands that need stdin (`nexus setup` -- already shipped,
  `nexus instance register` confirmations, `nexus plugins upgrade
  --family` w/o `--yes`) raise `InteractiveRequiredError` with
  **exit code 2** when `caps.profile == PLAIN` AND no explicit
  bypass flag.
* Exit code 2 matches typer convention (usage error). v1 specified
  3 which shadowed POSIX `diff`; v2 corrects.

### Dead-code deletion (NEW in v2)

The following modules + dep are scheduled for deletion in the new
epic's Story 00:

* `pypager` runtime dep in `pyproject.toml`
* `src/nexus/ui/components/paged_table.py` (PagedTable -- zero
  consumers)
* `src/nexus/ui/components/pager.py` (PagerProtocol +
  PypagerPager -- zero consumers)
* ratchet baselines for the three modules above
* Reexports from `src/nexus/ui/components/__init__.py`

An ADR ("FramedViewer (Textual) supersedes pypager for sticky-frame
paging") records the architectural reversal.

### Testing

* Test fakes: `FakeBatchProgress` records `start_batch / start_item
  / update_item / finish_item` calls and exposes a `console`
  property bound to `Console(file=StringIO())`. Same DI pattern as
  `KeychainClient` / `FakeKeychainClient`.
* TTY routing tested via `Console(force_terminal=True/False,
  file=StringIO())`.
* `EmaPriorStore` concurrent writes tested with two threads (real
  threading + tempfile). Cross-process is documented as out of
  scope.
* 100% line coverage on all new code; mypy strict + pyright strict
  + ruff + black all zero errors; no `# type: ignore`.

## Out of Scope (anti-creep fence)

* Custom termios / msvcrt scroller.
* `--pager / --no-pager / --limit / --no-color` flags. The single
  `--plain` flag covers the only intent we trust.
* Runtime profile switching mid-command. Terminal resize during a
  5-minute batch may leave the table slightly miscolumned -- known
  trade-off.
* Hard-coded per-family ETA priors. First batch shows
  "estimating..." until item 2 completes.
* Mouse / clickable rows. (FramedViewer keyboard navigation only.)
* User-customizable color themes. `NO_COLOR=1` and `--plain` are
  the only knobs.
* Migrating every existing command's output to RenderContext.
  Only FramedViewer-routed commands (`plugins list`, `plugins
  outdated`), batch-progress (`plugins upgrade`), and `nexus
  status` use RenderContext. Migration of other commands is a
  follow-on roadmap item.
* Persisting UI state between command invocations (cursor
  position, last viewed page, scroll offset).
* Replay trail / action history feature.
* Inline diff frame after destructive commands.
* Async-streaming row updates.
* Attaching `RenderContext` to the `Console` object via attribute
  injection (pyright strict rejects this).
* Profile-detection caching across NEXUS invocations.
* **Cross-process atomicity of `EmaPriorStore` (NEW).** v1 covers
  in-process multi-threaded writes only. Two concurrent NEXUS
  invocations on Windows MAY interleave JSONL lines. Recorded as a
  known trade-off; ADR can re-open if production traffic
  warrants.
* **pypager / PagedTable / PagerProtocol / PypagerPager (NEW --
  superseded).** Scheduled for deletion in Story 00 of the
  batch-progress epic. FramedViewer is the canonical paging path.

## Acceptance Criteria

### Shipped (verified on main)

* [x] `nexus plugins list` on a modern TTY renders through
      FramedViewer with sticky header, virtual scroll, `/`
      inline filter, sort, `r` refresh.
* [x] `nexus plugins list` on legacy_windows OR `--plain` renders
      inline DataTable.
* [x] `nexus plugins list --plain` on a TTY forces inline render.
* [x] `NEXUS_PLAIN=1 nexus plugins list` forces inline render.
* [x] `nexus status` shows a "Terminal" panel with the detected
      profile and inputs.

### Pending (driven by `.primer/epics/2026.05-cli-ux-batch-progress/`)

* [ ] pypager + PagedTable + PagerProtocol + PypagerPager are
      deleted; pyproject.toml no longer pins pypager; ratchet
      baselines for the deleted modules are removed; ADR records
      the reversal.
* [ ] `EmaPriorStore` records `{family, duration_s, ts}` to
      `~/.nexus/cache/eta_prior.jsonl`. First write creates the
      cache directory if absent.
* [ ] `EmaPriorStore.load(family)` returns up to 1000 most-recent
      entries; skips malformed JSONL lines.
* [ ] Concurrent in-process writes (two threads, 50 lines each)
      preserve all 100 records.
* [ ] `WeightedETAColumn` renders "ETA: estimating..." until item 2
      completes; from item 2 onward renders "ETA: MM:SS" computed
      with alpha=0.4 EMA blend.
* [ ] `make_batch_progress(ctx, total=N)` returns `RichBatchProgress`
      for RICH/BASIC and `PlainBatchProgress` for LEGACY/PLAIN.
* [ ] `PluginExecutor.upgrade(plugin_id, progress=bp)` and
      `PluginExecutor.batch_upgrade(targets, progress=bp)` route
      output through `bp.console.print`.
* [ ] Calling both methods with `progress=None` preserves today's
      behavior exactly.
* [ ] `nexus plugins upgrade <id>` on RICH/BASIC profile displays
      a Rich progress bar tracking SN's reported percent with
      WeightedETA column.
* [ ] `nexus plugins upgrade --family X` on RICH/BASIC profile
      displays an overall bar (M of N, weighted ETA) plus a
      transient per-item bar.
* [ ] `nexus plugins upgrade --family X` on LEGACY/PLAIN profile
      prints one completion line per item with elapsed time.
* [ ] `nexus plugins upgrade --family X` without `--yes` on PLAIN
      profile raises `InteractiveRequiredError` with **exit code 2**.
* [ ] All new code has 100% line coverage in the ratchet.
* [ ] mypy strict + pyright strict + ruff + black all report 0
      errors; no `# type: ignore` introduced.

## Success Metrics

* Zero CLI flags added beyond `--plain` (verified by `--help`
  scan).
* Time-to-find-a-plugin in a 500-row FramedViewer list: under 5
  seconds using `/` inline filter. (Shipped.)
* ETA accuracy on a 17-item batch upgrade: median absolute error
  across items 3..N under 25% of actual duration. (Pending.)
* Zero regression in CI / piped output (verified by smoke tests).

## Dependencies

* ADRs: one PENDING -- "FramedViewer (Textual) supersedes pypager
  for sticky-frame paging." Drafted as part of Story 00 in the
  batch-progress epic.
* Other PRDs: none.
* Existing code modules: `src/nexus/ui/components/framed_viewer.py`,
  `src/nexus/ui/components/table.py`,
  `src/nexus/ui/components/progress.py`, `src/nexus/ui/theme.py`,
  `src/nexus/ui/banner.py`, `src/nexus/cli/views.py`,
  `src/nexus/cli/__init__.py`, `src/nexus/cli/console.py`,
  `src/nexus/plugins/executor.py`, `src/nexus/plugins/progress.py`,
  `src/nexus/capabilities/status_reporter.py`.
* Runtime deps in pyproject.toml: `textual ^8.2.6` (already
  pinned, used by FramedViewer). `pypager ^3.0.1` is removed in
  Story 00.

## Out of Library Scope (always)

* We do not own the terminal emulator. ANSI / truecolor / window
  resize / pseudo-tty behavior is the emulator's job.
* We do not own the keychain (already abstracted via
  `KeychainClient`).
* We do not own the network. SN progress polling is
  `ProgressPoller`'s job; we just visualize its output.

## Open Questions

* None blocking implementation. All user-facing decisions resolved
  in v1 + v2 reconciliation. See
  `.primer/brainstorming/2026-05-18-cli-ux-implementation-plan.md`
  for the full pivot trail. Implementation epic is
  `.primer/epics/2026.05-cli-ux-batch-progress/`.
