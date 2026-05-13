# NEXUS -- Active Work

Last updated: 2026-05-12
Session: plugin management roadmap complete (sub-projects A-L + E, 13 slices merged). 780 tests passing.

## Current focus

Plugin command UAT in progress. User wants every `nexus plugins ...`
command and option validated individually, with issues tracked, then a
bug-chase pass to trace root causes and propose remediations.

The Python codebase itself is at a clean rest-state on main: all
roadmap-enumerated plugin sub-projects are shipped, both /simplify
rounds have been applied, and the last merge (#28) bumped coverage
ratchet baselines.

## Recent Changes

- #28 chore/plugins-simplify-trailing-five -- five trailing /simplify items
  (_today() helper, isolate_home into conftest, single-plugin explain
  filter, lightweight baselines list parse, orphans kwarg-only)
- #27 chore/plugins-simplify-klje -- post-merge /simplify cleanups for K+L+J+E
- #26 feat/plugins-ai-recommendations (E) -- AgentClient-backed recommend
  deactivate, explain, roadmap subcommands
- #25 feat/plugins-impact-cross-scope (J) -- cross-scope FK scan in
  compute_impact with --no-cross-scope CLI opt-out
- #24 feat/plugins-multi-baseline-drift (L) -- named baselines + plugins
  baselines list/delete subcommands

## Open Blockers

- Plugin command validation pass not yet started (user request).
- MCPProbe._check_server() still stubbed.
- PDI access-token cap (glide.oauth.access_token.expire_in.system_max_seconds)
  keeps tokens at 30 min regardless of token_lifetime request.
- knowledge/mastery/ empty.

## Next Steps

1. Walk every `nexus plugins` subcommand and option; log defects to a
   tracking file in this session.
2. Run a bug-chase to root-cause each defect; propose remediations.
3. Pivot back to active roadmap: `nexus setup` -> GitHubSync ->
   TemplateRegistry (per .primer/roadmap.md 2026.05).

## Branch / remote state

main: d7d5b66 (PR #28 merged). No active feature branch.
