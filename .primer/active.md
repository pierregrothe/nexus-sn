# NEXUS -- Active Work

Last updated: 2026-05-19
Session: shipped the CLI UX batch-progress epic top-to-bottom. The
brainstorm pivot caught PRD-001's "no Textual" anti-creep fence
silently broken on day one (FramedViewer + Textual landed in the
same commit as the PRD). PRD-001 v2 reconciles with reality;
ADR-024 records the FramedViewer-supersedes-pypager reversal;
Story 00 deletes ~250 LOC of dead pypager/PagedTable code; stories
01-05 build EmaPriorStore + WeightedETAColumn +
BatchProgressProtocol + executor.upgrade(progress=) +
nexus plugins upgrade wiring with InteractiveRequiredError exit-2.
1367 tests passing.

## Current Focus

Clean rest-state on main at bfd8cb9 (just pushed via 3 commits:
c75de7c primer, 363c1cb dead-code+pre-existing-fixes, bfd8cb9
batch-progress feature). The `2026.05-setup-sync` phase is now
done. No open epic. Next major capability target is either:

* `2026.06-template-library` -- builds on the sync v1 foundation;
  `template-apply-engine` would close the loop from
  `nexus sync` -> `nexus templates` -> `nexus apply <template>`.
* `2026.06-assessment` -- consumes the capture layer; bigger scope
  (RuleEngine + AssessmentReporter + Gate 1/2 + `nexus assess`).

Recommendation: pick Template Library first (smaller scope, gives
sync a concrete consumer, validates the apply pattern before
Assessment builds on it).

## Recent Changes

- bfd8cb9 feat(plugins): adaptive batch-progress + weighted ETA for nexus plugins upgrade
- 363c1cb chore: Story 00 -- delete pypager+PagedTable dead code + pre-existing fixes
- c75de7c primer: CLI UX brainstorm pivot + batch-progress epic + ADR-024
- 592d525 primer: sync after setup + sync epics shipped
- 1021038 feat(sync): nexus sync v1 catalog index + working nexus templates

## Open Blockers

- Claude Code CLI >= 2.0.0 required -- hard runtime dependency via SDK.
- MCPProbe._check_server() still stubbed; enterprise MCP endpoints unknown.
- knowledge/mastery/ empty (decision pending: copy from JARVIS or rebuild).
- `nexus assess`, `apply`, `run`, `rollback` still raise NotImplementedError.
- Template schemas under `src/nexus/templates/schemas/` are still stubs
  (deliberate -- v1 sync only validates the catalog manifest, not
  individual template YAMLs; schemas land with `template-apply-engine`).
- Plugin deactivate / uninstall are SN-platform-blocked (no API);
  CLI commands present as forward-compatible stubs.
- Plugin install/upgrade for offering plugins (sn_hs_*, sn_fs_*) is
  SN-platform-blocked at the OAuth/REST boundary; NEXUS detects and
  surfaces a clean failure message.

## Next Steps

1. Template Library: `template-apply-engine` + first 3 community
   templates -- builds on sync v1 we just shipped, completes the
   `2026.06-template-library` phase.
2. Assessment layer: `RuleEngine` + `AssessmentReporter` +
   `nexus assess` + Gate 1 (readiness) + Gate 2 (validation).
3. Distribution path (2026.08): pyproject metadata + README +
   PyPI publish for the `nexus-sn` package.

## Branch / remote state

main: bfd8cb9 (origin/main in sync). No active feature branch.
