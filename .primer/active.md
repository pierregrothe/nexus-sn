# NEXUS -- Active Work

Last updated: 2026-05-16
Session: shipped brew/apt-style CLI redesign (`plugins outdated` +
`plugins upgrade` with `--family` / `--all`), added transparent OAuth
token refresh inside `ServiceNowClient`, made plugin upgrades
idempotent (SN "already installed" -> success not failure), and
split `cli.py` into a focused 17-module `cli/` package per ADR-023.
1072 tests passing.

## Current Focus

Clean rest-state on main at 8528230 (just pushed). The plugin-management
CLI surface is now stable and self-consistent: read-only verbs (`outdated`,
`list`, `info`, `diff`) are clearly separated from destructive verbs
(`install`, `upgrade`, `apply`, `activate`), matching the brew/apt
muscle memory the user explicitly asked for. Long-running family batches
no longer die from PDI's 30-min OAuth token cap -- the client now
refreshes the bearer proactively (within 60s of expiry) and reactively
(once on 401). 403s are left alone since ACL denial cannot be fixed
by a fresh token.

All five quality gates are green: pytest (1072 passed, 1 skipped), ruff,
mypy strict, pyright strict, black. File-size ratchet baseline is empty
-- every file under the 800-line ADR-023 cap.

Next implementation target: `nexus setup` credential wizard, or `nexus
sync` to pull templates from the GitHub registry. The token-staleness
concern in `_rescan_plugin_inventory` (still uses the original token
variable even when the live client has refreshed mid-batch) is a known
follow-up but not user-visible.

## Recent Changes

- 8528230 feat(cli): brew-style outdated/upgrade + idempotent upgrade + mid-batch token refresh
- 2510b22 primer: scaffold sprint-status.yaml from roadmap checkboxes
- 59bf713 primer: sync after batch upgrade + governance ADRs landed
- 8314fa9 test(smoke): cover every documented `nexus plugins updates` combination
- 0b1a844 fix: clear all pre-existing mypy/pyright errors in tests/ (PR #50)

## Open Blockers

- Claude Code CLI >= 2.0.0 required -- hard runtime dependency via SDK.
- MCPProbe._check_server() still stubbed.
- knowledge/mastery/ empty.
- setup, sync, templates, assess raise NotImplementedError.
- Plugin deactivate / uninstall are SN-platform-blocked (no API exists);
  CLI commands present as stubs.

## Next Steps

1. nexus setup credential wizard (next implementation target).
2. nexus sync + GitHubSync + TemplateRegistry.
3. Assessment layer (RuleEngine + AssessmentReporter + nexus assess).
4. Optional: token-staleness fix in `_rescan_plugin_inventory` (cosmetic).

## Branch / remote state

main: 8528230 (origin/main in sync). No active feature branch.
