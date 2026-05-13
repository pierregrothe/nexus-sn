# NEXUS -- Active Work

Last updated: 2026-05-13
Session: CLI UI library + plugin UAT pass complete. 824 tests passing.

## Current focus

Codebase is at a clean rest-state on main (ae3d582, PR #32). All plugin
management sub-projects are shipped, plugin UAT defects are fixed, and the
unified CLI UI library (ui/components/) is complete and wired across all
commands.

Ready to pivot to the 2026.05 active roadmap: `nexus setup` credential
wizard is the next feature to build.

## Recent Changes

- #32 fix/scanner-latest-version -- read available_version field; diagnose
  missing latest_version data with clear error guidance
- #31 feat/cli-help-leaf-commands -- themed help panel on bare invocation
  for every leaf command (badge + options table + examples)
- #30 feat/cli-themed-command-guides -- themed two-box discovery view for
  sub-app no-args entry (instance, capture, plugins, templates, assess)
- #29 fix/plugins-uat-defects -- resolved 7 defects found during plugin
  command UAT (drift --ack persistence, baselines list parsing, diff
  output, recommend exit codes, export CSV, info unknown-plugin error)

## Open Blockers

- MCPProbe._check_server() still stubbed.
- PDI access-token cap (glide.oauth.access_token.expire_in.system_max_seconds)
  keeps tokens at 30 min regardless of token_lifetime request.
- knowledge/mastery/ empty.
- setup, sync, templates, assess commands raise NotImplementedError.

## Next Steps

1. nexus setup command -- credential wizard, config write, initial sync.
2. GitHubSync -- manifest fetch + template download from GitHub.
3. TemplateRegistry -- list and get from local cache.

## Branch / remote state

main: ae3d582 (PR #32 merged). No active feature branch.
