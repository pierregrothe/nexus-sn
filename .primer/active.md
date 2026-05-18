# NEXUS -- Active Work

Last updated: 2026-05-18
Session: investigated SN offering-plugin install path against alectri,
proved it is structurally unreachable via OAuth/REST, shipped clean
detection + actionable failure message, added `nexus instance
diagnose-roles` + `plugins outdated` auto-refresh + age display, then
stripped all the dead diagnostic plumbing now that the conclusion is
documented. 1105 tests passing.

## Current Focus

Clean rest-state on main at 26a0e9e (just pushed). The offering-plugin
gap is now closed at the documentation level: NEXUS detects SN's
offering-required error and surfaces `"Offering plugin (install via SN
UI -- AJAX-only path, OAuth/REST cannot dispatch)"` instead of leaking
the raw glide stack trace. The architectural reason -- `AppUpgrader.
installAndUpdateApps` hardcoding `jumboAppArgs=undefined` on line 1042,
while the real path lives in `AppUpgradeAjaxProcessor` reachable only
via `/xmlhttp.do` with session cookies that OAuth Bearer cannot obtain
-- is captured on the `OFFERING_PLUGIN_FAILURE_MESSAGE` constant
docstring so future contributors do not re-walk the search.

`nexus instance diagnose-roles` is the new way to self-diagnose ACL
denials: probes a fixed set of admin-only tables and reports 200/403/
404 per table. Replaces the previous hand-waved "you need role X"
hints. `nexus plugins outdated` now auto-refreshes inventory older
than 15 minutes (force with `--refresh`) and footers a humanised
captured-at via the new `humanize_age` utility.

All five quality gates green: pytest 1105 / pyright src/ 0 / mypy
strict 0 / black clean / ruff has one pre-existing error in
`src/stubs/pypager/source.pyi:8` (UP043) that is unrelated to this
work and was already on the branch.

Next implementation target stays `nexus setup` credential wizard, or
`nexus sync` to pull templates from the GitHub registry.

## Recent Changes

- 26a0e9e feat: diagnose-roles + outdated auto-refresh + offering detection
- 8528230 feat(cli): brew-style outdated/upgrade + idempotent upgrade + mid-batch token refresh
- 2510b22 primer: scaffold sprint-status.yaml from roadmap checkboxes
- 59bf713 primer: sync after batch upgrade + governance ADRs landed
- 8314fa9 test(smoke): cover every documented `nexus plugins updates` combination

## Open Blockers

- Claude Code CLI >= 2.0.0 required -- hard runtime dependency via SDK.
- MCPProbe._check_server() still stubbed.
- knowledge/mastery/ empty.
- setup, sync, templates, assess raise NotImplementedError.
- Plugin deactivate / uninstall are SN-platform-blocked (no API exists);
  CLI commands present as stubs.
- Plugin install/upgrade for offering plugins (sn_hs_*, sn_fs_*) is
  SN-platform-blocked at the OAuth/REST boundary; NEXUS detects and
  surfaces a clean failure message pointing users at the SN UI.

## Next Steps

1. nexus setup credential wizard (next implementation target).
2. nexus sync + GitHubSync + TemplateRegistry.
3. Assessment layer (RuleEngine + AssessmentReporter + nexus assess).
4. Optional: pre-existing UP043 ruff error in src/stubs/pypager/
   source.pyi:8 (one fix, unrelated to feature work).

## Branch / remote state

main: 26a0e9e (origin/main in sync). No active feature branch.
