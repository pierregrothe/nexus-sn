# Roadmap

## Foundation [done]
- [x] Config, auth, capabilities layers
- [x] ServiceNow REST connector + error hierarchy
- [x] ConnectorProtocol plugin system
- [x] CLI skeleton (all 5 commands stubbed)
- [x] CI/CD: lint, tests, release, template validation
- [x] Test suite foundation (39 tests, all real fakes)

## 2026.05 -- MVP Commands [active]
- [ ] AnthropicClient.complete() with prompt caching [active]
- [ ] GitHubSync -- manifest fetch + template download
- [ ] TemplateRegistry -- list and get from local cache
- [ ] InstanceScanner -- health scan via ServiceNowClient
- [ ] RuleEngine + AssessmentReporter
- [ ] nexus setup command -- credential wizard
- [ ] nexus status command -- probe capabilities, verify SN

## 2026.06 -- Template Library [planned]
- [ ] NowAssistSkill + Workflow Pydantic schemas
- [ ] First 3+ community templates in templates/
- [ ] Template apply engine (ApplyEngine)
- [ ] Gate 1 readiness check + Gate 2 validation check

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
