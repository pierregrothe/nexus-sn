# NEXUS -- Active Work

Last updated: 2026-05-14
Session: plugin batch upgrade shipped (`updates --apply [--family]`);
two governance ADRs codifying lessons from the work; black now in the
post-edit hook. 911 tests.

## Current Focus

Clean rest-state on main at 9a08211. The plugin batch upgrade landed
via PR #48 -- skip-on-fail batch over the existing
`PluginExecutor.upgrade` primitive, family filter via the curated
ProductFamily taxonomy, structured YAML report for CI. Three flags
extend `nexus plugins updates` without a new top-level command.

PR #49 closed three governance gaps surfaced by that work:
black is now in the post-edit hook (CI no longer the first place we
discover formatting drift); ADR-021 codifies the @model_validator
pattern for derived fields on frozen Pydantic models (over
@computed_field, which trips mypy strict's prop-decorator check);
ADR-022 codifies the # noqa: PLC0415 exception inside Typer command
bodies.

Next implementation target: `nexus setup` credential wizard, or
`nexus sync` to pull templates from the GitHub registry.

## Recent Changes

- 9a08211 governance: black in post-edit hook + ADR-021/022 from batch-upgrade lessons (PR #49)
- 9f5da5b feat(plugins): batch upgrade via `updates --apply [--family]` (PR #48)
- f7057b7 chore: refresh coverage.json after 887-test pass
- 0aafa0c docs(readme): extend plugin management diagram with execution lifecycle
- 184cfcc primer: sync after sub-projects M + N shipped

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

main: 9a08211. No active feature branch.
