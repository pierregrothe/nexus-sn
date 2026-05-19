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

## 2026.06 -- Assessment [planned]
- [ ] RuleEngine + AssessmentReporter (consuming CaptureResult)
- [ ] nexus assess command
- [ ] Gate 1 readiness check + Gate 2 validation check

## 2026.06 -- Template Library [planned]
- [ ] NowAssistSkill + Workflow Pydantic schemas
- [ ] First 3+ community templates in templates/
- [ ] Template apply engine (ApplyEngine)

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
