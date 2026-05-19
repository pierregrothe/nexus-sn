# NEXUS -- Active Work

Last updated: 2026-05-19
Session: shipped both 2026.06 epics end-to-end -- Assessment
(2026-05-19 commits 5bb9081..b733de2, 7 stories) and Template
Library (2026-05-19 commits 471cbbf..87a73c4, 7 stories + 1
primer commit). RuleEngine + Gate1Readiness + Gate2Validation +
HealthScan + nexus assess CLI. NowAssistSkill + Workflow schemas
with `{{ env.X }}` validators; render_to_records; ApplyEngine that
bundles via UpdateSetWriter into sys_update_set with NEXUS
provenance metadata; nexus apply CLI orchestrator wiring Gate 1 ->
ApplyEngine -> Gate 2 (PASS=0, BLOCK=2, ERROR=1). 3 example
templates + 3 per-template readiness rulesets + CI validator
script. PRD-002 (Assessment) and PRD-003 (Template Library) at
status=draft.

## Current Focus

Clean rest-state on main at 87a73c4 (origin/main in sync). Both
2026.06 phases done. Test count 1497 -> 1622 -> 1624 (collect
delta from extra sub-tests via parametrization).

Next major capability target candidates:

* `2026.07-agent-specialists` -- 8 domain specialists +
  ExecutionContext enrichment via enterprise MCP + Planner /
  Dispatcher orchestration + rollback manager. Largest scope of
  the remaining phases.
* `2026.08-distribution` -- 100% line coverage push + README +
  PyPI publish. Smallest scope; finishes the package.
* Backlog -- DEVELOPER_PLATFORM capture group; NiceGUI; knowledge
  mastery KB; MCPProbe real endpoints.

Recommendation: 2026.08 distribution first to ship a v1 on PyPI
before Agent Specialists adds another multi-week scope.

## Recent Changes

- 87a73c4 feat(templates): Story 07 -- example templates + CI
- 9217629 feat(cli): Story 06 -- nexus apply orchestrator
- 4dd5f16 feat(templates): Story 05 -- ApplyEngine + ApplyResult
- d6fa327 feat(templates): Story 04 -- render_to_records
- 0471851 feat(templates): Story 03 -- TemplateDocument + loader

## Open Blockers

- Claude Code CLI >= 2.0.0 required -- hard runtime dependency via SDK.
- MCPProbe._check_server() still stubbed; enterprise MCP endpoints unknown.
- knowledge/mastery/ empty (decision pending: copy from JARVIS or rebuild).
- `nexus run`, `nexus rollback` still raise NotImplementedError.
- `nexus apply --live` capture-runner and ApplyEngine factory in
  default_apply_collaborators() raise NotImplementedError until a
  configured ServiceNowClient + CaptureEngine pairing is wired
  (test wiring covers the contract end-to-end against
  FakeServiceNowClient).
- Plugin deactivate / uninstall are SN-platform-blocked (no API);
  CLI commands present as forward-compatible stubs.
- Plugin install/upgrade for offering plugins (sn_hs_*, sn_fs_*) is
  SN-platform-blocked at the OAuth/REST boundary; NEXUS detects and
  surfaces a clean failure message.

## Next Steps

1. Pick 2026.07 Agent Specialists OR 2026.08 Distribution.
   Distribution is the smaller commit; agent specialists is the
   larger capability.
2. Wire the production ApplyEngine factory in
   `default_apply_collaborators()` -- requires a configured
   ServiceNowClient + CaptureEngine + nexus_version + git_sha at
   process boot.
3. Same for the `--live` capture_runner in `commands_apply.py`
   and `commands_assess.py` (Assessment Story 06 stubs).
4. Backlog hygiene: DEVELOPER_PLATFORM capture group, NiceGUI,
   MCPProbe real endpoints.

## Branch / remote state

main: 87a73c4 (origin/main in sync). No active feature branch.
