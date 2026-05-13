# NEXUS -- Active Work

Last updated: 2026-05-13
Session: plugin execution design + release 2026.05.2 + Gantt sync. 827 tests.

## Current focus

Codebase is at a clean rest-state on main (7308a96). Plugin execution design
(sub-projects M + N) is approved and specced. Release 2026.05.2 is tagged and
the GitHub Actions wheel is built. Gantt diagram in README.md now regenerates
automatically from .primer/roadmap.md on every /primer sync.

Sub-project M (plugin execution core) is the next implementation target.

## Recent Changes

- 7308a96 feat(scripts): sync Gantt from .primer/roadmap.md on /primer sync
- 73d8645 docs(specs,roadmap): plugin execution design -- sub-projects M + N
- 60f8154 docs(roadmap): add plugin apply engine to 2026.07 (then moved to 2026.05)
- bcac380 chore(release): bump version to 2026.05.2
- 09b76df feat(skills/release): bump version + update docs before tagging

## Open Blockers

- MCPProbe._check_server() still stubbed.
- PDI access-token cap keeps tokens at 30 min regardless of token_lifetime.
- knowledge/mastery/ empty.
- setup, sync, templates, assess commands raise NotImplementedError.
- README stubs list: templates_cmd in cli.py vs templates in README (naming gap).

## Next Steps

1. Sub-project M: PluginExecutor + ProgressPoller + install/activate/upgrade/apply
2. Sub-project N: deactivate/uninstall + mandatory impact gate
3. nexus setup credential wizard (after M+N)

## Branch / remote state

main: 7308a96. No active feature branch.
