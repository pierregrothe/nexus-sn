# NEXUS -- Active Work

Last updated: 2026-05-18
Session: shipped two full epics back-to-back -- `nexus setup`
credential wizard (commits 1eca36f + fd0f0df) and `nexus sync` v1
catalog index + working `nexus templates` (commit 1021038). Each
epic went through the brainstorm + adversarial-review + epic
decomposition flow before implementation. 1303 tests passing.

## Current Focus

Clean rest-state on main at 1021038 (just pushed). The two former
NotImplementedError stubs in the `2026.05-setup-sync` phase are now
real:

* `nexus setup` -- idempotent first-run wizard. Probes the OS
  keychain, scans `~/.nexus/instances/` for existing profiles, and
  dispatches to clean-slate / inline-reauth / already-configured /
  corrupted-profile branches. Every prompt routes through a typed
  `PromptSource` Protocol so tests use `ScriptedPromptSource` with
  zero `unittest.mock`. `provision_oauth` is now idempotent on a
  deterministic `nexus-<profile>` SN entity name -- Ctrl-C between
  OAuth creation and token exchange no longer accumulates duplicate
  oauth_entity records on retry; the next run finds and PATCH-rotates
  the existing secret.
* `nexus sync` -- pulls a manifest from
  `https://raw.githubusercontent.com/<repo>/<branch>/templates/
  manifest.json` and caches it locally with a UTC `cached_at` stamp.
  Wire vs cached models are separate (adversarial-review fix: a
  single `extra="forbid"` model would have broken round-trip
  serialization). Never-raises client mirrors the
  `GitHubReleasesClient` pattern; `validate_github_repo` rejects URLs
  and malformed slugs before any HTTP. `nexus templates` reads the
  cache and renders a Rich DataTable, falling back to a Hint when no
  prior sync has run.

All five quality gates green: pytest 1303 / pyright src/ 0 / mypy
strict 0 / ruff 0 / black clean. The pre-existing UP043 ruff error
in `src/stubs/pypager/source.pyi:8` was fixed mid-session (rolled
into commit 1eca36f).

The next implementation target is the assessment layer
(`RuleEngine` + `AssessmentReporter` + `nexus assess`) for the
`2026.06-assessment` phase, or `template-apply-engine` for
`2026.06-template-library` which now has the sync foundation.

## Recent Changes

- 1021038 feat(sync): nexus sync v1 catalog index + working nexus templates
- fd0f0df feat(setup): stories 5-7 complete the nexus setup credential wizard
- 1eca36f feat(setup): foundations 1-4 for nexus setup credential wizard
- dee8167 primer: sync after offering investigation + diagnose-roles ship
- 26a0e9e feat: diagnose-roles + outdated auto-refresh + offering detection

## Open Blockers

- Claude Code CLI >= 2.0.0 required -- hard runtime dependency via SDK.
- MCPProbe._check_server() still stubbed; enterprise MCP endpoints unknown.
- knowledge/mastery/ empty (decision pending: copy from JARVIS or rebuild).
- `nexus assess`, `apply`, `run`, `rollback` still raise NotImplementedError.
- Template schemas under `src/nexus/templates/schemas/` are still stubs
  (deliberate -- v1 sync only validates the catalog manifest, not
  individual template YAMLs; schemas land with `template-apply-engine`).
- Plugin deactivate / uninstall are SN-platform-blocked (no API);
  CLI commands present as forward-compatible stubs.
- Plugin install/upgrade for offering plugins (sn_hs_*, sn_fs_*) is
  SN-platform-blocked at the OAuth/REST boundary; NEXUS detects and
  surfaces a clean failure message.

## Next Steps

1. Assessment layer (RuleEngine + AssessmentReporter + `nexus assess`)
   -- next major feature in phase `2026.06-assessment`.
2. `template-apply-engine` + first 3 community templates -- builds on
   the sync foundation just shipped, completes the
   `2026.06-template-library` phase.
3. `cli-paged-list-widget` (ready in sprint-status) and
   `cli-batch-progress-eta` (backlog) -- UI improvements in the
   current `2026.05-setup-sync` phase but separate from the
   feature-shipping path.

## Branch / remote state

main: 1021038 (origin/main in sync). No active feature branch.
