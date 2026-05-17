---
id: PRD-001
title: CLI UX wow factor -- adaptive rendering + batch progress with ETA
status: draft
date: 2026-05-15
adrs: []
charter_link: charter.md
milestone: 2026.05-setup-sync
---

# PRD-001: CLI UX wow factor -- adaptive rendering + batch progress with ETA

## Problem

`nexus plugins list` dumps 500+ rows in a single non-scrollable
table -- annoying for a human to consume, no sticky header, no
search. Long-running operations (`nexus plugins upgrade <id>`,
`nexus plugins updates --apply`) display no progress feedback, no
ETA, no batch-level "X of N complete." Plugin upgrades observed in
production range 30 s -- 15 min each, making any batch operation
feel like a black box. The user explicitly wants modern, colorful,
dynamic CLI UX inspired by `gh`, `glab`, `lazygit`, `btop`, and
expects **one entrypoint** -- the tool detects the terminal's
capabilities at startup and picks the best rendering strategy
automatically, with no user-facing flags to think about.

## Users

- Human operators running NEXUS interactively in modern terminals
  (Windows Terminal, iTerm, gnome-terminal, kitty, VS Code).
- Human operators on legacy environments (pre-Windows-Terminal
  cmd.exe, tmux/screen multiplexers with limited ANSI support).
- CI pipelines invoking NEXUS in non-TTY mode (auto-degrade to
  plain text, no pager, line-per-event progress).
- Operators piping NEXUS output to grep / awk / further pipelines
  (force PLAIN profile via `--plain` flag).

## In Scope (must-haves)

### Capability detection

- A `TerminalCapabilities` frozen Pydantic model built once at
  startup in `make_console()`. Fields:
  - `is_tty` -- stdout AND stderr both isatty
  - `is_ci` -- any of `$CI`, `$GITHUB_ACTIONS`, `$JENKINS_HOME`,
    `$GITLAB_CI`, `$BUILDKITE`, `$CIRCLECI`, `$TRAVIS`, `$DRONE`,
    `$TF_BUILD` (Azure Pipelines)
  - `color_depth` -- StrEnum NONE / ANSI16 / ANSI256 / TRUECOLOR
    derived from Rich's `console.color_system`
  - `cols, rows` -- terminal size via `shutil.get_terminal_size()`
    with fallback `(80, 24)` on OSError
  - `legacy_windows` -- Rich's `console.legacy_windows`, suppressed
    to False when `$WT_SESSION` or `$ITERM_SESSION_ID` is set
  - `term_program` -- `$TERM_PROGRAM` env var (no fallback)
  - `is_dumb_terminal` -- `$TERM == "dumb"` OR Rich's check
  - `is_multiplexer` -- `$TERM` starts with `tmux` or contains
    `screen`, unless `$COLORTERM == "truecolor"`
  - `no_color_env` -- `$NO_COLOR` is set (any value)
  - `forced_plain` -- result of `_argv_has_plain()` OR
    `$NEXUS_PLAIN` is set
  - `supports_hyperlinks` -- Rich's `Console.options.legacy_windows`
    inverse, gated on color_depth >= ANSI256

- A `RenderProfile` StrEnum with four values, picked by a pure
  function `pick_profile(caps) -> RenderProfile`:
  - `RICH` -- caps.is_tty AND caps.color_depth is TRUECOLOR AND
    caps.rows >= 24 AND NOT caps.is_ci AND NOT caps.no_color_env
    AND NOT caps.legacy_windows AND NOT caps.forced_plain AND
    NOT caps.is_dumb_terminal AND NOT caps.is_multiplexer
  - `BASIC` -- caps.is_tty AND caps.color_depth >= ANSI16 AND
    NOT caps.legacy_windows AND NOT caps.forced_plain
    AND NOT caps.is_dumb_terminal (RICH conditions failed but
    we still have a color-capable TTY)
  - `LEGACY` -- caps.is_tty AND (caps.legacy_windows OR
    caps.color_depth is NONE) AND NOT caps.forced_plain
  - `PLAIN` -- otherwise (non-TTY, dumb terminal, CI, --plain,
    NEXUS_PLAIN, or piped output)

- A `RenderContext` frozen `@dataclass(slots=True)` holding
  `(console, caps, profile)`. Built by `make_console()`, attached
  to the Typer `Context` via `ctx.obj`, retrieved via the helper
  `get_render_context(ctx) -> RenderContext`.

### Single entrypoint

- ONE user-facing flag: `--plain` (force PLAIN profile,
  intent-revealing alias for "no color, no pager, machine
  readable").
- Standard env-var conventions honored: `$NO_COLOR`, `$TERM=dumb`,
  and our own `$NEXUS_PLAIN=1`.
- NO `--pager`, NO `--no-pager`, NO `--limit`, NO `--no-color`
  CLI flags. The tool decides.

### `nexus status` extension

- The existing `nexus status` command grows a "Terminal" panel
  (alongside Identity, System, Integrations, Diagnostics)
  showing the detected profile and the inputs that drove it:
  `Profile: RICH | TTY: yes | CI: no | Color: TRUECOLOR | Size:
  120x40 | Terminal: WindowsTerminal | Pager: pypager`.
  Discoverability without a new entrypoint.

### Rendering components

- `PagedTable` (frozen Pydantic) that takes a `RenderContext` in
  its `render(ctx)` method and dispatches by profile:
  - RICH/BASIC: `pypager` when `len(rows) > caps.rows - 4`,
    else inline DataTable
  - LEGACY: ASCII-box DataTable, inline (no pager -- pypager
    requires VT escapes that legacy cmd.exe lacks)
  - PLAIN: tab-separated rows, one per line, suitable for piping

- `BatchProgressProtocol` with two implementations:
  - `RichBatchProgress` (RICH/BASIC profiles): Rich `Progress`
    with overall task + transient per-item tasks, brand spinner,
    `WeightedETAColumn`
  - `PlainBatchProgress` (LEGACY/PLAIN profiles): one status line
    per item completion via `console.print` -- no Live region,
    no `\r` rewrites (multiplexer-safe), no progress bar
  - Factory: `make_batch_progress(ctx, total) ->
    BatchProgressProtocol`

- Pager backend: `pypager` (pure-Python, MIT, ~5 KB). Only invoked
  in RICH/BASIC profiles.

- `WeightedETAColumn` blending SN-reported in-flight percent with
  an EMA (alpha=0.4) of completed-item durations. Display
  "ETA: estimating..." until item 2 completes. No hard-coded
  family priors.

- `EmaPriorStore` recording `{family, duration_s, ts}` to an
  append-only JSONL file at `~/.nexus/cache/eta_prior.jsonl`.
  Multi-writer safe by construction. Capped at 1000 entries with
  truncate-oldest on read.

- ASCII glyph palette (`[ok] [!!] [..] [->] [*]`) paired with
  theme styles. Color-graded severity helper (`severity_color(
  score)` HSL hue 120->0). Middle-truncation helper for long
  plugin IDs.

### Refactoring

- `PluginExecutor.batch_upgrade` accepts an injected
  `BatchProgressProtocol | None` (None preserves current
  behavior).
- `PluginExecutor.upgrade` (single-item path) accepts the same
  optional injection.
- `make_console()` performs an `_argv_has_plain()` pre-scan of
  `sys.argv` so the Console is built before Typer parses argv.

### Interactive-required commands

- Commands that need stdin (`nexus setup`, `nexus instance
  register` confirmations, `nexus plugins updates --apply`
  without `--yes`) raise `InteractiveRequiredError` exit-3 when
  `caps.profile == PLAIN AND NOT explicit-bypass-flag`.

### Testing

- Test fakes: `FakePager` records the renderable handed to
  `page()`; `FakeBatchProgress` records `start_item /
  update_item / finish_item` calls. Same DI pattern as
  `KeychainClient` / `FakeKeychainClient`.
- TTY routing tested via `Console(force_terminal=True/False,
  file=StringIO())`.
- 100% line coverage on all new code; mypy strict + pyright
  strict + ruff + black all zero errors; no `# type: ignore`.

## Out of Scope (anti-creep fence -- the load-bearing section)

- We will NOT add Textual as a dependency. The TUI app paradigm
  is wrong for one-shot CLI commands. If a `nexus tui`
  interactive app is ever built, it gets its own PRD.
- We will NOT add a custom termios / msvcrt scroller.
- We will NOT add `--pager / --no-pager / --limit / --no-color`
  flags. The single `--plain` flag covers the only intent we
  trust (machine-readable output). All other rendering is
  detected automatically.
- We will NOT support runtime profile switching mid-command.
  Terminal resize during a 5-minute batch may leave the table
  slightly miscolumned; this is a known trade-off documented in
  the architecture, not a feature gap.
- We will NOT hard-code per-family ETA priors. First batch
  shows "estimating..." until item 2 completes.
- We will NOT support mouse / clickable rows / cell selection.
- We will NOT support user-customizable color themes (`NO_COLOR=
  1` and `--plain` are the only knobs).
- We will NOT audit and migrate every existing command's output
  to the new RenderContext pattern in this PRD. Only the new
  components (PagedTable, BatchProgress, pager) and the
  `nexus status` Terminal panel are in scope. Other commands
  (existing `nexus status` panels, `nexus capture` output,
  `nexus instance` output) keep current Rich behavior. Migration
  to RenderContext is a follow-on roadmap item.
- We will NOT persist UI state between command invocations
  (cursor position, last viewed page, scroll offset).
- We will NOT add a "replay trail" / action history feature in
  this PRD.
- We will NOT add an inline diff frame after destructive
  commands.
- We will NOT add async-streaming row updates.
- We will NOT support attaching the `RenderContext` to the
  `Console` object via attribute injection (pyright strict
  rejects this and we honor the strict gate).
- We will NOT implement profile-detection caching across NEXUS
  invocations -- detection is cheap (<1 ms) and re-running it
  per command keeps the model honest under shell-config changes.

## Acceptance Criteria

- [ ] `nexus plugins list` on a modern TTY auto-pages with
      pypager when `len(rows) > caps.rows - 4`; renders inline
      otherwise. No `--pager` flag in `--help`.
- [ ] `nexus plugins list` redirected to a file emits PLAIN
      profile output: tab-separated rows, no ANSI escapes, no
      pager invocation.
- [ ] `nexus plugins list --plain` on a TTY forces PLAIN
      profile output regardless of detection.
- [ ] `NEXUS_PLAIN=1 nexus plugins list` on a TTY forces PLAIN
      profile output regardless of detection.
- [ ] `NO_COLOR=1 nexus plugins list` on a TTY drops color but
      keeps the pager (BASIC profile path).
- [ ] `nexus plugins list` on pre-Win10 cmd.exe (legacy_windows
      true) renders ASCII-box DataTable inline (no pager
      invocation, no ANSI escapes).
- [ ] `nexus plugins upgrade <id>` on RICH/BASIC profile displays
      a Rich progress bar tracking SN's reported percent with
      WeightedETA column. On LEGACY/PLAIN profile, prints a
      single status line per progress poll cycle.
- [ ] `nexus plugins updates --apply` on RICH/BASIC profile
      displays an overall bar (M of N, weighted ETA) plus a
      transient per-item bar. On LEGACY/PLAIN profile, prints one
      completion line per item with elapsed time.
- [ ] Item 1 of any batch displays "ETA: estimating..." until
      item 2 completes.
- [ ] `EmaPriorStore` survives two concurrent `nexus plugins
      updates --apply` invocations without data loss.
- [ ] `nexus status` shows a "Terminal" panel with the detected
      profile and inputs.
- [ ] `nexus setup` invoked under PLAIN profile (CI / pipe)
      raises `InteractiveRequiredError` with exit code 3.
- [ ] All new code has 100% line coverage in the ratchet.
- [ ] mypy strict + pyright strict + ruff + black all report 0
      errors after the change; no `# type: ignore` introduced.
- [ ] `RenderContext` is plumbed through Typer's `ctx.obj`,
      never via attribute injection on the `Console`.

## Success Metrics

- Zero CLI flags added beyond `--plain` (counted in `--help`
  output).
- Time-to-find-a-plugin in a 500-row list: under 5 seconds
  using pager `/search`.
- ETA accuracy on a 17-item batch upgrade: median absolute error
  across items 3..N under 25% of actual duration.
- Zero regression in CI / piped output (verified by smoke tests).

## Dependencies

- ADRs: none yet. The "RenderContext via Typer ctx.obj over
  Console attribute injection" choice may earn an ADR during
  implementation.
- Other PRDs: none.
- Existing code modules: `src/nexus/ui/components/table.py`,
  `src/nexus/ui/components/progress.py`, `src/nexus/ui/theme.py`,
  `src/nexus/ui/banner.py`, `src/nexus/cli.py`,
  `src/nexus/plugins/executor.py`,
  `src/nexus/plugins/progress.py`,
  `src/nexus/capabilities/status_reporter.py`.
- New runtime dep: `pypager` (pure-Python, MIT, ~5 KB).

## Out of Library Scope (always)

- We do not own the terminal emulator. ANSI / truecolor / window
  resize / pseudo-tty behavior is the emulator's job.
- We do not own the system pager. We bundle `pypager` and use it
  exclusively.
- We do not own the keychain (already abstracted via
  `KeychainClient`).
- We do not own the network. SN progress polling is
  `ProgressPoller`'s job; we just visualize its output.

## Open Questions

- None blocking implementation. All user-facing decisions
  (single entrypoint, four-tier profile model, `--plain` as the
  only knob, adversarial round 2 hits) resolved. See
  `.primer/brainstorming/2026-05-15-cli-ux-wow-factor.md` for the
  full design trail.
