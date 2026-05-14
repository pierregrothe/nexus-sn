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

## 2026.05 -- Setup + Sync [active]
- [ ] nexus setup command -- credential wizard, config write, initial sync
- [ ] GitHubSync -- manifest fetch + template download
- [ ] TemplateRegistry -- list and get from local cache

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
