# NEXUS -- Active Work

Last updated: 2026-05-13
Session: README sync script complete. 833 tests passing.

## Current focus

Codebase is at a clean rest-state on main (47cc076). The README sync
script (`scripts/sync_readme.py`) is complete and wired into `/primer sync`
as Step 8. Pre-edit hook now blocks emoji/icon characters while explicitly
allowing Rich box-drawing (U+2500-U+257F).

Ready to pivot to the 2026.05 active roadmap: `nexus setup` credential
wizard is the next feature to build.

## Recent Changes

- 47cc076 fix(scripts): guard zero test count, fix stub warning, export __all__
- 4a184e8 docs(readme): update test count to 832 and add tests anchor
- a7e0ba2 feat(scripts): sync_readme.py -- auto-update README on /primer sync
- 84194af chore: fix README version placeholder + add scripts/ to pythonpath
- 614d4ce docs(plans): README sync implementation plan

## Open Blockers

- MCPProbe._check_server() still stubbed.
- PDI access-token cap (glide.oauth.access_token.expire_in.system_max_seconds)
  keeps tokens at 30 min regardless of token_lifetime request.
- knowledge/mastery/ empty.
- setup, sync, templates, assess commands raise NotImplementedError.
- README stubs list (4 commands) diverges from cli.py stubs (7 commands:
  apply, assess, rollback, run, setup, sync, templates). Needs manual fix.

## Next Steps

1. Fix README stubs list to match cli.py (add apply, rollback, run).
2. nexus setup command -- credential wizard, config write, initial sync.
3. GitHubSync -- manifest fetch + template download from GitHub.

## Branch / remote state

main: 47cc076. No active feature branch.
