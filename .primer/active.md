# NEXUS -- Active Work

Last updated: 2026-05-15
Session: cleared all pre-existing mypy/pyright errors in tests/ (PR
#50); extended `nexus plugins updates` smoke coverage to every option
permutation (16/16 green live); ran progressive destructive batch
upgrade on retail PDI (Level 1-5 fully + Level 6 partial). 912 tests.

## Current Focus

Clean rest-state on main at 8314fa9. The plugin batch upgrade feature
is now exhaustively covered live: 16 smoke tests cover every documented
combination of `nexus plugins updates` and run green against alectri;
the destructive `--apply --yes` path was demonstrated end-to-end
against the retail PDI in six progressive levels, including a real
skip-on-fail capture (`sn_grc_advanced` failed with "Application
version is currently installed" and the loop continued).

Type-checking gates are tight: mypy strict + pyright strict + ruff +
black all 0 errors across src/ AND tests/ (was 12 mypy + 53 pyright
errors before PR #50). `# type: ignore` is now provably absent across
the codebase.

Next implementation target: `nexus setup` credential wizard, or
`nexus sync` to pull templates from the GitHub registry.

## Recent Changes

- 8314fa9 test(smoke): cover every documented `nexus plugins updates` combination (16/16 live)
- 1e6aa8d chore: refresh README test badge to 912
- 54b60a4 fix(scripts): sync_readme detects @app.command("name") explicit name
- 0b1a844 fix: clear all pre-existing mypy/pyright errors in tests/ (PR #50)
- 347fe38 primer: sync after batch upgrade + governance ADRs landed

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

main: 8314fa9. No active feature branch.
