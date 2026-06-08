# NEXUS -- Active Work

Last updated: 2026-06-08
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

## Current Focus

Schema Cartographer complete on `feature/2026.06-schema-cartographer`.
Test count 1624 -> 1665. New layer at 100% line coverage (protocol excluded,
matching capture.protocol). mypy + pyright strict 0; ruff + black clean.
Live ERDs generated in docs/erd/ for all three areas against `alectri`.

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

## Recent Changes

- c967a74 chore(schema): ratchet coverage baselines for nexus.schema
- b482008 docs(schema): generated ERDs (doc-designer, bcm, cmdb-bcm)
- 5fd6b8d feat(cli): nexus schema areas/erd commands
- 7698e8e feat(schema): SchemaProtocol + SchemaCartographer engine
- ae61396 feat(schema): SchemaDiscoverer with validated cell normalization

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

1. Merge `feature/2026.06-schema-cartographer` (open PR or fast-forward).
2. Optionally write ADR-025 (schema layer) + PRD-004 (schema cartographer).
3. Use the doc-designer ERD + narrative to draft the CS9240769 case reply
   (confirm the UI "Fields" tab maps to `sn_grc_doc_design_data_column`).
4. Pick 2026.07 Agent Specialists OR 2026.08 Distribution next.
5. Schema fast-follow: record-level config-trace mode.

## Branch / remote state

feature/2026.06-schema-cartographer: c967a74 (not yet merged to main).
main: 87a73c4 (origin/main in sync).
