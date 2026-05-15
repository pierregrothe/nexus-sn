# NEXUS -- Active Work

Last updated: 2026-05-14
Session: plugin execution sub-projects M + N shipped end-to-end; smoke
suite expanded to 55 tests; deactivate/uninstall investigation closed.
887 tests.

## Current Focus

Codebase is at a clean rest-state on main (f79b556). Plugin execution
core (sub-project M) and destructive ops (sub-project N) merged this
session via PRs #38, #39. Smoke suite live-tested against the alectri
PDI is at 55/55 passing.

The deactivate/uninstall investigation is closed with a definitive
finding: ServiceNow does not expose these operations via any
programmatic API on Yokohama (Bearer REST, session-cookie xmlhttp.do,
table API, GraphQL, SDK -- all confirmed unavailable). The CLI commands
remain in the tree as forward-compatible stubs; see spec addendum
2026-05-14e for the full source trail.

Next implementation target: `nexus setup` credential wizard, or
`nexus sync` to pull templates from the GitHub registry.

## Recent Changes

- ffed9a5 feat(plugins): batch upgrade via `nexus plugins updates --apply [--family]`
- f79b556 perf(plugins): cache impact-gate inventory snapshot (PR #47)
- 4d22702 docs(plugins): exhaustive web research confirms uninstall is impossible by SN design (PR #46)
- c154ecf docs(plugins): AppsAjaxProcessor is not public; uninstall is UI-only (PR #45)
- b8c2b6a docs(plugins): definitive findings on deactivate/uninstall via SN metadata mining (PR #44)
- 7f68cc0 docs(plugins): document live capture of App Manager Uninstall flow (PR #43)

## Open Blockers

- Claude Code CLI >= 2.0.0 required -- hard runtime dependency via SDK.
- MCPProbe._check_server() still stubbed.
- PDI access-token cap keeps tokens at 30 min.
- knowledge/mastery/ empty.
- setup, sync, templates, assess raise NotImplementedError.
- Plugin deactivate / uninstall are SN-platform-blocked (no API exists);
  CLI commands present as stubs.

## Next Steps

1. nexus setup credential wizard (next implementation target).
2. nexus sync + GitHubSync + TemplateRegistry.
3. Assessment layer (RuleEngine + AssessmentReporter + nexus assess).

## Branch / remote state

main: f79b556. No active feature branch.
