# NEXUS -- Active Work

Last updated: 2026-06-09
Session: shipped the Schema Cartographer (`nexus.schema`) layer end-to-end
on branch `feature/2026.06-schema-cartographer` (commits 8e47e31..c967a74,
12 tasks). Driver: support case CS9240769 (RONA) -- reverse-engineer a live
ServiceNow data dictionary into Mermaid ERDs to answer the Document Designer
Fields/Data Relationships/Content Configuration question and produce reusable
BCM and CMDB<->BCM table maps. New read-only layer 5 (parallel to capture/
assessment): SchemaDiscoverer (sys_scope -> sys_db_object -> sys_dictionary /
sys_relationship), frozen SchemaGraph models, JSON archive, MermaidErdEmitter,
SchemaCartographer behind SchemaProtocol, and `nexus schema areas|erd` CLI.
Three areas seeded (doc-designer, bcm, cmdb-bcm). Validated live against
`alectri` before building (94 reference edges, 42 cross-scope). Design spec +
12-task plan under docs/superpowers/.

Then added -- and later retired -- the Schema Mindmap mode (`nexus schema
mindmap <area>`): an AI-enriched, business-domain-grouped table catalog
(Mermaid mindmap + "Stores X" descriptions), built via brainstorm -> spec ->
7-task subagent TDD (modules catalog/enricher/mindmap_emitter; TableEnricher
made one batched AgentClient call to cluster + describe, with a
scope-grouping fallback). It was retired by user decision in commit c96f1a8
on `feature/2026.06-schema-image-export`: the ERD now carries each table's
key fields inside the entity boxes (1feb198), which answers the "which table
stores what" question in one artifact, so the mindmap modules, the CLI
command, and the docs/mindmaps/ outputs were deleted.

Also fixed two pre-existing test-suite bugs that made the full `pytest`
"slow and failing": an INTERNALERROR crash (test_ui_capabilities patched the
global shutil.get_terminal_size that pytest's progress renderer calls) and a
Windows hang (test_runner_logs_when_re_exec_fails missing @skipif(win32) ran a
nested pytest). Perf: removed forced --cov from addopts (~3.5x), added
pytest-xdist (`-n auto` in CI/pre-commit) + pytest-timeout, lowered conftest
logging to WARNING.

## Current Focus

Schema Cartographer merged to main via PR #51. Current work on
`feature/2026.06-schema-image-export`: Kroki image export for ERDs
(`nexus schema erd <area> --image svg|png`, `--kroki-url` / `NEXUS_KROKI_URL`,
`--kroki-timeout`; KrokiClient in api/), ERD entity boxes now carry key
fields (PK, business columns, FK references), and cmdb-bcm rebuilt as a true
CMDB<->BCM bridge view. The mindmap mode is retired (c96f1a8, user decision)
-- the fields-in-boxes ERD is the single schema deliverable. mypy + pyright
strict 0; ruff + black clean. Live ERDs in docs/erd/ for all three areas
against `alectri` (images git-ignored, reproducible via `--image`).

Known tooling landmine (pre-existing, Windows-local): `pytest --cov` errors at
collection on `mcp`'s pydantic RootModel under coverage.py 7.13.5 -- affects
CLI-test coverage measurement only (schema-module coverage + the ratchet are
unaffected; tests pass without --cov). Worth a separate look (coverage omit or
a version pin) before relying on local full-coverage runs.

Key validated finding (corrects the customer hypothesis): Document Designer
is a three-level hierarchy Template -> Content Configuration [-> Data
Relationship] -> Fields. `data_rel_mapping` (Content config) references both
`template_config` and `data_relationship`; `data_column` (Fields) references
`data_rel_mapping` -- Fields are NOT standalone. CMDB bridge confirmed via
`sn_bcp_recovery_task.configuration_item -> cmdb_ci`.

Next major capability target candidates (unchanged from prior session):

* `2026.07-agent-specialists` -- 8 domain specialists + ExecutionContext
  enrichment + Planner/Dispatcher + rollback manager. Largest scope.
* `2026.08-distribution` -- 100% line coverage push + README + PyPI publish.
  Smallest scope; finishes the package.
* Schema fast-follows -- record-level config-trace (walk a real OOB template's
  Fields/Data Rel/Content Config records); `nexus schema diff`; per-scope ERD
  splitting for large areas; more areas (CSM/ITSM/HRSD).
* Schema local rendering -- replace Kroki with a local graphviz renderer
  (Python graphviz package + binary, DOT format). Requires rewriting
  MermaidErdEmitter to a GraphvizErdEmitter behind the same KrokiClientProtocol
  interface; SVG produced offline with no network dependency. User preference:
  graphviz over mmdc (avoids Node.js).

## Recent Changes

- c96f1a8 refactor(schema): retire mindmap mode -- ERD is the schema deliverable
- 1feb198 feat(schema): ERD entities render key fields (PK/business/FK columns)
- c96453d feat(schema): cmdb-bcm is now a true CMDB<->BCM bridge view
- c1ad24e feat(schema): nexus schema erd|mindmap --image svg|png via Kroki
- 7462fb3 feat(schema): add KrokiClient for diagram image rendering
- f44073c Merge pull request #51 (schema cartographer -> main)

## Open Blockers

- ADR-025 for the schema layer not yet written (optional; layer follows the
  established capture/ pattern). PRD-004 (schema cartographer) optional.
- Full pytest suite is slow to *execute* on this Windows box (~7+ min for
  1665 tests); collection is fast (1.9s, 0 import errors). Not a correctness
  issue -- targeted suites and static checks are all green.
- Claude Code CLI >= 2.0.0 required -- hard runtime dependency via SDK.
- MCPProbe._check_server() still stubbed; enterprise MCP endpoints unknown.
- knowledge/mastery/ empty (decision pending: copy from JARVIS or rebuild).
- `nexus run`, `nexus rollback` still raise NotImplementedError.
- `nexus apply --live` capture-runner and ApplyEngine factory in
  default_apply_collaborators() raise NotImplementedError until a configured
  ServiceNowClient + CaptureEngine pairing is wired.
- **sys_update_xml direct-REST POST is blocked by SN ACL** even for admin via
  OAuth Bearer (affects `nexus apply` and `nexus capture push`). See
  decisions.md 2026-05-19 entry + backlog "ApplyEngine v2".
- Plugin deactivate/uninstall and offering-plugin install/upgrade are
  SN-platform-blocked at the OAuth/REST boundary; surfaced as clean failures.

## Next Steps

1. Merge `feature/2026.06-schema-image-export` (Kroki export +
   fields-in-boxes ERD + mindmap retirement).
2. Optionally write ADR-025 (schema layer) + PRD-004 (schema cartographer).
3. Use the doc-designer ERD + narrative to draft the CS9240769 case reply
   (confirm the UI "Fields" tab maps to `sn_grc_doc_design_data_column`).
4. Pick 2026.07 Agent Specialists OR 2026.08 Distribution next.
5. Schema fast-follow: record-level config-trace mode.

## Branch / remote state

feature/2026.06-schema-cartographer: merged to main via PR #51 (f44073c).
feature/2026.06-schema-image-export: c96f1a8 (not yet merged to main).
