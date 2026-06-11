# Roadmap

## Foundation [done]
- [x] Config, auth, capabilities layers
- [x] ServiceNow REST connector + error hierarchy
- [x] ConnectorProtocol plugin system
- [x] Instance management (register, connect, refresh, list, delete, use + OAuth auto-provisioning)
- [x] CLI skeleton (all commands wired)
- [x] CI/CD: lint, tests, release, template validation
- [x] AgentClient backed by claude-agent-sdk
- [x] nexus status command
- [x] nexus.capture layer (ScopeDiscoverer, ConfigFetcher, ArchiveWriter/Reader,
      UpdateSetXmlBuilder, UpdateSetWriter, CaptureEngine)
- [x] nexus capture command (discover, pull, list, push)
- [x] nexus.plugins layer -- 13 sub-projects (inventory, diff, updates, advisories,
      orphans, impact, cleanups, drift, inventory-refinements, cross-scope,
      multi-baseline, advisory-overrides, AI-recommendations) + UAT defect fixes
- [x] nexus plugins command -- full subapp (scan, list, info, inventory, impact,
      advisories, orphans, diff, updates, drift, baselines, recommend, export)
- [x] Unified CLI UI library (ui/components/ -- StatusBadge, KeyValuePanel,
      DataTable, CommandGuide, Hint, Notice; themed discovery views + leaf help)

## 2026.05 -- Plugin Execution [done]
- [x] Sub-project M: Plugin execution core -- nexus plugins install / activate /
      upgrade / apply <plan.yaml>; PluginExecutor + ProgressPoller + OperationResult;
      sn_appclient probe with app-management + v_plugin fallback; rollback on
      partial apply-plan failure
- [x] Sub-project N: Destructive operations -- nexus plugins deactivate / uninstall;
      mandatory impact gate (block on non-zero reverse deps / cross-scope refs);
      --force escape with double confirmation; base plugin uninstall refused
      (live action paths blocked by SN platform -- see spec addendum 2026-05-14e)
- [x] Batch upgrade -- `nexus plugins updates --apply [--family ...]` with
      skip-on-fail; reuses sub-project M's PluginExecutor.upgrade primitive.

## 2026.05 -- Setup + Sync [done]
- [x] nexus setup command -- credential wizard, config write, initial sync
      Epic: epics/2026.05-nexus-setup-wizard/
      Brainstorm: brainstorming/2026-05-18-nexus-setup-credential-wizard.md
      Start: epics/2026.05-nexus-setup-wizard/01-prompt-source.story.md
- [x] GitHubSync -- manifest fetch + template download
      Epic: epics/2026.05-nexus-sync-catalog/
      Brainstorm: brainstorming/2026-05-18-nexus-sync-catalog.md
      Start: epics/2026.05-nexus-sync-catalog/01-template-models.story.md
- [x] TemplateRegistry -- list and get from local cache
      Epic: epics/2026.05-nexus-sync-catalog/
- [x] CLI adaptive list rendering -- superseded by FramedViewer
      (Textual). See ADR-024. PRD-001 v2 (2026-05-18) records
      the architectural reversal; pypager + PagedTable removed
      as dead code in Story 00 of the batch-progress epic.
      PRD: prd/PRD-001-cli-ux-wow-factor.md
      ADR: adr/ADR-024-framedviewer-supersedes-pypager.md
- [x] CLI adaptive batch progress with weighted ETA --
      BatchProgressProtocol with RichBatchProgress (RICH/BASIC)
      and PlainBatchProgress (LEGACY/PLAIN); WeightedETAColumn +
      EmaPriorStore (JSONL); single-item + batch bars driven by
      ServiceNow's reported percent blended with EMA of
      completed-item durations
      PRD: prd/PRD-001-cli-ux-wow-factor.md
      Epic: epics/2026.05-cli-ux-batch-progress/
      Brainstorm: brainstorming/2026-05-18-cli-ux-implementation-plan.md
      Start: epics/2026.05-cli-ux-batch-progress/01-ema-prior-store.story.md

## 2026.06 -- Assessment [done]
- [x] RuleEngine + AssessmentReporter (consuming CaptureResult)
      PRD: prd/PRD-002-nexus-assessment.md
      Epic: epics/2026.06-nexus-assessment/
      Brainstorm: brainstorming/2026-05-19-nexus-assessment-rule-engine.md
      Start: epics/2026.06-nexus-assessment/01-rule-schemas-and-yaml-loader.story.md
- [x] nexus assess command
- [x] Gate 1 readiness check + Gate 2 validation check

## 2026.06 -- Template Library [done]
- [x] NowAssistSkill + Workflow Pydantic schemas
      PRD: prd/PRD-003-nexus-template-library.md
      Epic: epics/2026.06-nexus-template-library/
      Brainstorm: brainstorming/2026-05-19-nexus-template-library.md
      Start: epics/2026.06-nexus-template-library/01-now-assist-skill-schema.story.md
- [x] First 3+ community templates in templates/
- [x] Template apply engine (ApplyEngine)

## 2026.06 -- Schema Cartographer [done]
- [x] nexus.schema layer -- SchemaDiscoverer (sys_scope -> sys_db_object ->
      sys_dictionary / sys_relationship), frozen SchemaGraph models, JSON
      archive, MermaidErdEmitter, SchemaCartographer behind SchemaProtocol
      Spec: specs/2026-06-08-schema-cartographer-design.md
      Plan: plans/2026-06-08-schema-cartographer.md
      Driver: support case CS9240769 (RONA) -- Document Designer answer +
      reusable BCM and CMDB<->BCM table maps
- [x] nexus schema command -- areas, erd; ERD entity boxes carry each
      table's key fields (PK + business columns + FK references)
- [x] Deterministic per-scope grouped ERD (--grouped) -- one Mermaid
      diagram per scope, byte-stable across runs, no LLM
- [x] Kroki image export (--image svg|png) + offline archive round-trip
      (--save-archive / --from-archive)
      Plan: plans/2026-06-08-schema-image-export.md
      Doc: docs/schema-image-export.md
- [x] Three seeded areas (doc-designer, bcm, cmdb-bcm) including the
      CMDB<->BCM bridge view
- [x] Schema product catalog -- replaced hardcoded areas.py with
      GitHub-synced products.json bundled in the package; nexus schema erd
      now accepts product names / acronyms / keys (1 or 2 products);
      nexus sync fetches catalog; nexus schema products command
      Spec: specs/2026-06-11-schema-product-catalog-design.md
      Plan: plans/2026-06-11-schema-product-catalog.md
      PR: #54

## 2026.07 -- Agent Specialists [planned]
- [ ] 8 domain specialist agents implemented
- [ ] ExecutionContext enrichment from enterprise MCP
- [ ] Multi-step orchestration via Planner + Dispatcher
- [ ] Rollback manager for failed deployments

## 2026.08 -- Distribution [planned]
- [ ] 100% line coverage, mypy strict, ruff 0 violations
- [ ] README + getting started documentation
- [ ] PyPI publish (nexus-sn)

## Backlog

### GRC License Management (nexus.licenses)

Driver: recurring customer support questions (e.g. Sergio) on GRC module
role classification -- which roles count as Operator / Lite Operator / Shared,
how many users are exposed, and whether the deployment is audit-ready.

- [ ] nexus licenses role-check <role_name> -- query
      sn_irm_shared_cmn_role_types directly and display the license class
      (Operator / Lite Operator / Shared) for any given role. Product-agnostic:
      works for any role on the instance, not restricted to a specific module.
- [ ] nexus licenses user-exposure [--role <name>] [--scope <scope_key>] --
      count active users who hold a given role (or group of roles) and group
      the results by owning application scope. Product-agnostic: the scope
      grouping is derived live from sys_scope on the instance rather than
      hardcoded to any product family. Useful for impact analysis before any
      deployment or role reassignment, regardless of the product involved.
- [ ] nexus assess grc-licensing -- walk all roles assigned on the instance
      (filtered by the GRC role classification table), cross-reference each
      with sn_irm_shared_cmn_role_types, and produce an exposure report:
      per-scope Operator / Lite Operator / Shared counts + affected user list.
      Scope grouping is dynamic from the instance, not hardcoded to any
      product. Proactive license audit surface before ServiceNow runs one.
- [ ] SSC integration for license validation -- when nexus detects a license
      question on instance data, automatically cross-reference against the SSC
      "Risk Pricing & Packaging" document via the existing MCP SSC server to
      validate the applicable rule and cite the source. Depends on MCPProbe
      real endpoint URLs (see below).

### Schema Fast-follows

- [ ] Local SVG rendering via graphviz -- replace Kroki dependency with a
      local graphviz renderer (Python graphviz package + binary). Requires
      rewriting MermaidErdEmitter to a GraphvizErdEmitter behind the same
      KrokiClientProtocol interface. Fully offline, no network dependency.
      (User preference: graphviz over mmdc -- avoids Node.js.)
- [ ] record-level config-trace -- walk a real OOB template's Fields /
      Data Rel / Content Config records to confirm the exact table chain
- [ ] nexus schema diff -- delta between two schema snapshots of the same area
- [ ] per-scope ERD splitting for large areas (separate file per scope)
- [ ] more areas: CSM, ITSM (scoped tables), HRSD

### Other Backlog
- [ ] NiceGUI web interface (nexus[ui] optional extra)
- [ ] Knowledge mastery KB (206 ServiceNow product docs)
- [ ] MCPProbe real endpoint URLs
- [ ] JIRA, GitHub, Confluence connectors
- [ ] Extend capture to DEVELOPER_PLATFORM table group
      (business rules, script includes, ACLs, scheduled jobs)
- [ ] Wire `/api/sn_appclient/appmanager/products?tab_context=updates`
      into scanner (alectri demo shows 269 product updates beyond the 762 apps)
- [ ] Plugin install/activate over REST via the discovered sn_appclient
      install lifecycle endpoints -- prerequisite for sub-projects M/N
- [ ] Mine the broader scripted-REST catalog (120 services / 218 ops, see
      docs/sn-internal-api-catalog.md) for assessment + automation features
      not currently reachable through the documented Table API
- [ ] ApplyEngine v2 -- direct-write or update-set-import path for OAuth
      Bearer environments. Live smoke 2026-05-19 found `sys_update_xml`
      ACL blocks direct REST POST even for admin via OAuth; same blocker
      hits the existing `nexus capture push`. See decisions.md 2026-05-19
      entry for the four options (direct-write / Import API / scripted
      REST / Basic auth).
