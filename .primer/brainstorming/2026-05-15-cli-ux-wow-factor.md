# Brainstorming: CLI UX wow factor (scrollable list + progress with ETA)

Date: 2026-05-15
Mode: assumptions (research-driven, skipped technique rounds)
Techniques: assumptions-mode + adversarial-review
Trigger: User wants two CLI UX features. Quote: "I want my users [to]
say 'Wow, what a great looking CLI tool'."

## Context Brief

NEXUS already ships a Rich-based UI layer in `src/nexus/ui/`:
DataTable (frozen Pydantic + GradientPanel), KeyValuePanel, two_col,
CommandGuide, Hint, Notice, StatusBadge, nexus_progress factory,
banner.py (gated on `console.is_terminal`). Theme tokens defined in
`theme.py`: SN_BLUE / SN_LIME truecolor stops, semantic styles
(label/value/ok/warn/error/border.*).

Rich >= 13.9 is already pinned in pyproject.toml. Textual is NOT a
dependency. The project is Python 3.14, ASCII-only, mypy strict +
pyright strict zero errors, 100% line coverage, no mocks (real fakes
only).

Two pain points motivated the brainstorm:

1. `nexus plugins list` renders 500+ rows eagerly at cli.py:1716 --
   annoying for humans to scroll, no sticky header, no in-pane search.
2. Long ops (`plugins upgrade <id>`, `plugins updates --apply` batch)
   poll SN's `/api/sn_appclient/appmanager/progress/{id}` but display
   no progress, no ETA, no "X of N done" for the batch case. The
   recent retail-PDI run showed individual plugin upgrades taking
   anywhere from 30 s to 15 min -- making ETA estimation non-trivial.

## Key Insights

1. **Don't add Textual.** It's a full TUI framework that owns the
   event loop. Every `nexus` command is one-shot -- render, exit.
   Textual costs ~3 MB of deps and refuses to run without a TTY,
   which breaks CI pipelines. The pattern that fits us is Rich +
   a tiny pure-Python pager, not Textual.

2. **Bundle `pypager`, not system `less`.** Author's original
   thought was Rich's `console.pager(styles=True)` which shells
   out to `less`. Stock Windows installs without Git Bash have no
   `less`; `cmd.exe` has no native pager with search. `pypager`
   is pure-Python, 5 KB, MIT, identical behavior on Windows /
   macOS / Linux. Same code path everywhere, no system-tool
   dependency.

3. **Rich's built-in ETA is wrong for our workload.** It's
   `(total - done) / samples_per_sec` over a fixed window --
   adequate for uniform work, terrible for plugin upgrades that
   vary 30 s to 15 min. The fix is a custom `WeightedETAColumn`
   that blends two signals: SN-reported in-flight percent +
   exponential moving average (alpha = 0.4) of completed-item
   durations. No hard-coded family priors (the adversarial review
   correctly rejected the "N=1 sample as prior" cargo-cult).

4. **The ratchet is paid.** Existing UI components observe frozen
   Pydantic discipline, fakeable I/O, ASCII-only glyphs. Two new
   components + one ProgressColumn subclass + one storage helper
   land cleanly in `src/nexus/ui/components/` without churning
   anything else.

5. **"Wow" is color + gradient + smart truncation -- not Unicode.**
   The ASCII-only project rule is not an obstacle. Color is the
   primary signal: lime ok / red error / dim pending / blue arrow
   / lime-bold active. Glyph is backup: `[ok]` / `[!!]` / `[..]` /
   `[->]` / `[*]` -- distinct shapes for NO_COLOR fallback. Combine
   with the existing truecolor gradient panels and brand spinner,
   and the result reads modern.

## Recommendations

1. **Build `PagedTable` component** at
   `src/nexus/ui/components/paged_table.py` (~120 LOC). Wraps
   the existing DataTable and routes rendering through a
   `PagerProtocol`. Auto-page on TTY + rows >= 50; inline on TTY
   + rows < 50; plain on not-TTY. `--pager / --no-pager /
   --limit N` flags on `plugins list` only.

   Rationale: matches `git log`, `gh`, `glab` defaults. Scoped to
   the one command that has the pain. Other long-list commands
   can adopt later without API change since `PagedTable` is the
   public abstraction.

2. **Build `BatchProgress` component** at
   `src/nexus/ui/components/batch_progress.py` (~180 LOC) using
   one shared Rich `Progress` instance. Outer "overall" task
   tracks N items; per-item tasks created with `transient=True`
   so they vanish on completion. All `console.print()` inside
   `batch_upgrade` re-routes through `progress.console.print()`
   so the Live region and inline prints interleave correctly.

   Rationale: solves the stdout-contention problem the
   adversarial review flagged. Rich Progress is already a transitive
   dep; using its built-in mechanism is simpler than rolling a
   custom layout.

3. **Build `WeightedETAColumn` + `EmaPriorStore`** at
   `src/nexus/ui/components/eta.py` (~100 LOC). EMA (alpha=0.4)
   over completed items, blended with `(1 - sn_pct) * ema_duration`
   for the in-flight item. Append-only JSONL cache at
   `~/.nexus/cache/eta_prior.jsonl` -- one record per item
   `{family, duration_s, ts}`. Multi-writer safe by construction.

   Rationale: alpha=0.4 converges 87% to steady state by item 5.
   JSONL kills the race-condition the adversarial review flagged
   (last-writer-wins on a JSON object).

4. **Add `Pager` + `FakePager` protocol pair** at
   `src/nexus/ui/components/pager.py` (~80 LOC). Production
   implementation delegates to `pypager`. `FakePager` records the
   renderable it was given.

   Rationale: same dependency-injection pattern as KeychainClient /
   FakeKeychainClient. Resolves the "how do we test pager routing
   without mocks" problem the adversarial review flagged.

5. **Add ASCII glyph palette + theme helpers** at
   `src/nexus/ui/glyphs.py` (~40 LOC) and extend
   `src/nexus/ui/theme.py` with `severity_color(score) -> str`
   (HSL hue 120->0) and `truncate_middle(s, width) -> str`.

   Rationale: small, contained, reusable across all commands. No
   hidden coupling.

6. **Refactor `PluginExecutor.batch_upgrade`** at
   `src/nexus/plugins/executor.py:670` to accept an injected
   `BatchProgress | None`. None = silent (CI / scripted use);
   BatchProgress = interactive display.

   Rationale: surgical change. Existing inline `console.print`
   calls flip to `progress.console.print` when progress is
   passed; behavior preserved when None.

## Trade-offs

| Option | Pro | Con | Position |
|--------|-----|-----|----------|
| Rich + pypager pager | Zero new system deps, same UX on Win/mac/Linux | One new Python dep (5 KB) | Chosen |
| Rich `console.pager()` (system less) | Zero new deps | Breaks on stock Windows | Rejected (adversarial hit) |
| Textual DataTable app | Native sticky header, mouse | 3 MB deps, needs TTY, breaks CI | Rejected |
| Custom termios scroller | Zero deps | 150 LOC + Win/Unix branch + test pain | Rejected |
| Rich Progress (overall + transient per-item) | Multi-task native, theme-able | Manual ETA column | Chosen |
| `tqdm.asyncio` | Best async ergonomics | Single-task, plain styling | Rejected |
| Custom WeightedETAColumn (EMA + SN pct) | Accurate on variable durations | ~100 LOC + tests | Chosen |
| Built-in Rich ETA | Free | Terrible on variable durations | Rejected |
| Built-in family priors | First-batch ETA shows a number | N=1 sample is cargo-cult | Rejected (adversarial hit) |
| "ETA: estimating..." until item 2 | Honest | First batch shows no number | Chosen |
| JSONL prior cache (append-only) | Multi-writer safe | Trim on read | Chosen |
| JSON dict prior cache | Smaller file | Race condition on concurrent writes | Rejected |
| Flags on 4 commands | Consistent surface | 4 x flag surface increase | Rejected |
| Flags on `plugins list` only | Surgical | Inconsistent with `scopes list` | Chosen (others can adopt later) |
| `[ok]/[!!]` ASCII glyphs paired with color | ASCII-rule-safe, NO_COLOR fallback | Less visually rich than emoji | Chosen |

## Out of Scope (explicit anti-creep fence)

- Textual TUI app (could revisit as a separate `nexus tui` command).
- Async-streaming row updates (scans return frozen `PluginInventory`).
- Mouse / clickable rows (requires Textual).
- User-customizable color themes (brand is brand; `NO_COLOR=1` is
  the only knob).
- Persistent UI state between commands (each invocation independent).
- Pager flags on `scopes list`, `plugins inventory`, `plugins
  updates` (deferred to a follow-on roadmap item).
- Replay trail / action history at the end of every command
  (interesting idea; deferred -- would benefit from telemetry first).
- Inline diff frame after destructive commands (deferred to a
  separate "destructive command UX polish" story).

## Open Questions

- None blocking implementation. The three user-facing decisions
  (pager default = auto, dep = pypager, story split = 2) were
  resolved via AskUserQuestion before this artifact was written.

## Adversarial Review

The `primer-adversarial` agent challenged the first synthesis and
flagged eight items. All addressed:

1. `less` absent on stock Windows -- replaced with `pypager` (pure
   Python, 5 KB).
2. Rich Live + existing `console.print()` stdout contention --
   refactor `batch_upgrade` to route all output through
   `progress.console.print()`.
3. Concurrent `eta_prior.json` write race -- switched to
   append-only JSONL.
4. Surface-area creep (4 commands x 4 flags) -- scoped to
   `plugins list` only.
5. Test strategy for pager routing absent -- defined
   `PagerProtocol` + `FakePager` in the same DI pattern as
   `KeychainClient`.
6. ETA prior is N=1 sample (cargo cult) -- dropped hard-coded
   priors entirely; show "ETA: estimating..." until item 2
   completes.
7. `[ok]/[!!]` visual indistinctness -- pair every glyph with a
   theme style; rely on color first, glyph second; distinct char
   widths for NO_COLOR fallback.
8. Three-branch TTY (ANSI / legacy cmd / not-TTY) -- trust Rich's
   `Console.legacy_windows` detection; the design only needs the
   `is_terminal` two-branch.

Two items the reviewer raised but were determined to be
non-issues:

- "Path getter side-effects" -- `NexusPaths.eta_prior_cache` is
  pure (returns a Path); the I/O lives in a separate
  `EmaPriorStore.record()`. Two-object split already matches the
  patterns.md rule.
- "Accessibility" of ASCII glyphs vs Unicode -- the rule is
  project-mandated and applies to all output; this design follows
  it. Color-first signaling is the accessibility lever.

## Research Findings Appendix

### Rich's pager mechanism

- `console.pager(styles=True)` returns a context manager that
  buffers all renders and ships them to `pydoc.pager()` on exit.
- `pydoc.pager` consults `PAGER` env var, then tries `less`, then
  `more`, then falls back to a plain print-with-page-prompt loop
  on Windows without external pagers.
- Source: https://rich.readthedocs.io/en/stable/console.html#paging
- Connects to: Recommendation #1 -- we bypass Rich's pager entirely
  in favor of pypager for consistent cross-platform behavior.

### Rich Progress multi-task model

- A single `Progress` instance can host multiple `Task` rows via
  `add_task()`. Tasks can be transient (vanish on completion) or
  persistent.
- The `Progress.console` attribute is the same Rich Console with
  awareness of the Live region -- `progress.console.print()`
  interleaves correctly with the live bars.
- Custom columns subclass `ProgressColumn` and implement
  `render(task) -> RenderableType`.
- Source: https://rich.readthedocs.io/en/stable/progress.html
- Connects to: Recommendations #2, #3 -- the architecture relies
  on both capabilities.

### EMA tuning for variable-duration CLI work

- alpha=0.5 used by alive-progress, alpha=0.3 used by tqdm
  smoothing parameter; alpha=0.4 is a midpoint chosen for our
  blend.
- Convergence: after `n` items, EMA is `1 - (1 - alpha)^n`
  fraction of the way to the steady-state mean. alpha=0.4, n=5
  -> 0.92; alpha=0.4, n=3 -> 0.78.
- Source: https://blog.mbedded.ninja/programming/signal-processing/digital-filters/exponential-moving-average-ema-filter/
- Connects to: Recommendation #3 -- EMA over arithmetic mean
  prevents single-outlier poisoning.

### ServiceNow progress-poll shape

- `/api/sn_appclient/appmanager/progress/{id}` returns either
  `{status, trackerId}` (kickoff response) or `{state, sys_id,
  percent}` (progress-poll response). The existing
  `ProgressPoller` already normalizes both shapes.
- The `percent` field is what we feed into the "in-flight item"
  half of the WeightedETAColumn formula.
- Source: `src/nexus/plugins/progress.py` + the retail-PDI
  destructive-test session 2026-05-14.
- Connects to: Recommendation #3 -- the (1 - sn_pct) term comes
  from here.

### `pypager` package

- Pure Python; depends only on the standard library.
- Supports sticky header line, less-style `/` search, `q` quit,
  Page-Up / Page-Down / arrow keys.
- License: MIT.
- Repo: https://github.com/prompt-toolkit/pypager
- Connects to: Recommendation #4 -- the pager backend.

## Session Notes

This session ran in assumptions-mode without technique rounds.
Two parallel research agents launched at start: one mapped the
existing `src/nexus/ui/` layer (DataTable, theme tokens, nexus_progress,
TTY detection); one researched Rich vs Textual vs prompt_toolkit +
ETA estimation algorithms. The adversarial agent then challenged
the resulting synthesis. Three user-facing decisions resolved via
AskUserQuestion: persistence routing (all four options), pager
backend choice (pypager), pager default behavior (auto on TTY +
rows >= 50). Total agent rounds: 4. Total user exchanges: 2.

---

## Refinement Round 2: single entrypoint + capability-based profile

After the initial synthesis was committed, the user pushed back
on the "multiple flags + multiple branches" shape. Quote: "I do
not want multiple entrypoints. Can we detect when we run nexus
what are the terminal capabilities and then use the system that
work best for the user?"

### Resulting design

- Detect terminal capabilities once at process startup in
  `make_console()` and build a frozen `TerminalCapabilities`
  Pydantic model.
- Pick exactly one `RenderProfile` from four tiers: RICH, BASIC,
  LEGACY, PLAIN.
- Bundle `(console, caps, profile)` into a frozen `RenderContext`
  dataclass, threaded through Typer's `ctx.obj`.
- Drop `--pager / --no-pager / --limit / --no-color` CLI flags.
- Keep ONE flag: `--plain` (force PLAIN profile), plus
  `$NEXUS_PLAIN=1` env var. Honor `$NO_COLOR` and `$TERM=dumb`.
- `BatchProgress` becomes a protocol with two implementations:
  `RichBatchProgress` (RICH/BASIC) and `PlainBatchProgress`
  (LEGACY/PLAIN). Picked by `make_batch_progress(ctx, total)`
  factory.

### Profile selection logic

| Profile | Trigger conditions |
|---|---|
| RICH | is_tty AND truecolor AND rows >= 24 AND NOT is_ci AND NOT no_color_env AND NOT legacy_windows AND NOT forced_plain AND NOT is_dumb_terminal AND NOT is_multiplexer |
| BASIC | is_tty AND color_depth >= ANSI16 AND NOT legacy_windows AND NOT forced_plain AND NOT is_dumb_terminal |
| LEGACY | is_tty AND (legacy_windows OR color_depth is NONE) AND NOT forced_plain |
| PLAIN | otherwise |

### Adversarial round 2 -- 13 hits, all addressed

1. Rich does not publicly expose `supports_hyperlinks` /
   `term_program` -- moved env-var-sourced fields into separate
   detection helpers; Rich attributes only come from documented
   public surface.
2. pypager works on Windows Terminal (ANSI), unreliable on
   pre-Win10 cmd.exe -- pypager confined to RICH/BASIC profiles.
3. Rich's `legacy_windows` misclassifies WT on Win11 in some
   contexts -- override to False when `$WT_SESSION` or
   `$ITERM_SESSION_ID` is set.
4. `os.get_terminal_size()` raises OSError on file redirect --
   wrap with `(80, 24)` fallback via `shutil.get_terminal_size`.
5. `--plain` ordering problem (Console built before Typer
   parses argv) -- pre-scan `sys.argv` via pure function
   `_argv_has_plain()`; Typer still validates the flag for help.
6. `is_interactive` field redundant -- replaced with `is_ci`
   sourced from 9 documented CI env vars.
7. Attribute injection on Console fails pyright strict --
   replaced with `RenderContext` dataclass threaded through
   `ctx.obj`; no attributes attached to Rich objects.
8. Profile picked once -- terminal resize mid-batch leaves
   slightly miscolumned output; documented as known trade-off.
9. Tmux/screen `\r` corruption -- `PlainBatchProgress` emits one
   full line per event, no carriage-return rewrites.
10. Multiplexer truecolor claims unreliable -- downgrade RICH ->
    BASIC under tmux/screen unless `COLORTERM=truecolor`.
11. Interactive-required commands (`nexus setup`,
    `plugins updates --apply` without `--yes`) under PLAIN
    profile -- raise `InteractiveRequiredError` exit-3.
12. `--plain` IS an entrypoint -- accepted as the single
    intent-revealing knob; all other detection is automatic.
13. Discoverability gap -- `nexus status` extended with a
    "Terminal" panel showing profile + inputs; no new command.

### Hits acknowledged as out of scope

- Migration of existing non-target commands (StatusReporter
  beyond the Terminal panel, capture, instance, agent commands)
  to RenderContext -- separate follow-on story.
- HTML report generation (`nexus assess`) -- file write, profile
  irrelevant.
- NiceGUI dashboard -- separate process, profile irrelevant.

### Net change to artifacts

- PRD-001 rewritten with capability-detection model + four-tier
  profile + RenderContext design.
- Story 01 expanded: now covers `TerminalCapabilities`,
  `RenderContext`, `make_console()`, argv pre-scan, the
  `nexus status` Terminal panel, plus the original PagedTable
  scope.
- Story 02 expanded: `BatchProgress` becomes a Protocol with two
  implementations (`RichBatchProgress`, `PlainBatchProgress`)
  picked by `make_batch_progress(ctx, total)` factory; covers
  interactive-required refusal.

### Total agent rounds and user exchanges

After refinement: 5 agent rounds (2 research + 2 adversarial +
1 user-decision-driven), 5 user exchanges across the full
session. Persisted: 1 brainstorm artifact + 1 PRD + 2 stories
+ roadmap inserts + sprint-status entries.
