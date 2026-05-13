# NEXUS -- Active Work

Last updated: 2026-05-13
Session: README badges + Gantt fixes + decisions.md corrections. 830 tests.

## Current Focus

Codebase is at a clean rest-state on main (b920af6). README now has a
shields.io badge row (Release, CI, License, Python, Tests, LOC) synced
automatically by /primer sync. Gantt Mermaid render errors on GitHub are
fixed. decisions.md corrected: Claude Code CLI >= 2.0.0 is a hard runtime
dependency (not optional).

Sub-project M (plugin execution core) is the next implementation target.

## Recent Changes

- b920af6 feat(scripts,readme): add badge row synced by /primer sync
- c25282c docs(decisions): correct three wrong Claude Code claims
- e2507b1 fix(scripts): one bar per section in Gantt -- labels always fit
- 63858ec fix(scripts): strip colons from Mermaid Gantt task names
- fd9ab6c fix(scripts): add required colon before dates in Mermaid Gantt

## Open Blockers

- Claude Code CLI >= 2.0.0 required -- hard runtime dependency via SDK.
- MCPProbe._check_server() still stubbed.
- PDI access-token cap keeps tokens at 30 min.
- knowledge/mastery/ empty.
- setup, sync, templates, assess, apply, run, rollback raise NotImplementedError.

## Next Steps

1. Sub-project M: PluginExecutor + ProgressPoller + install/activate/upgrade/apply
2. Sub-project N: deactivate/uninstall + mandatory impact gate
3. nexus setup credential wizard

## Branch / remote state

main: b920af6. No active feature branch.
