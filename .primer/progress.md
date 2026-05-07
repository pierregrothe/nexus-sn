# Progress

## What Works

Config layer:
  NexusPaths -- XDG-compliant path resolution (~/.nexus/*, ~/.config/nexus/*)
  NexusConfig -- Pydantic model (frozen) for config.yaml
  ConfigManager -- read/write with env var override support

Auth layer:
  KeychainClient + FakeKeychainClient -- OS keychain via keyring
  ClaudeAuth -- Claude Enterprise API key retrieval
  SNAuth -- ServiceNow credentials retrieval
  AuthError hierarchy

Capabilities layer:
  FeatureFlag, MCPServer enums
  FEATURE_MAP -- maps features to required MCP servers
  ProbeResult, CapabilitySet -- startup capability state

Connectors layer:
  ConnectorProtocol -- plugin interface
  ConnectorRegistry -- dynamic connector loading
  ServiceNowClient + FakeServiceNowClient -- REST API (table, record, scripting endpoints)
  ServiceNowConnector -- protocol implementation
  Full error hierarchy (SNAuthError, SNNotFoundError, SNRateLimitError, SNServerError)

Agents base:
  AgentProtocol, ExecutionContext, AgentResult

CLI skeleton:
  All 5 MVP commands present in cli.py (setup, status, sync, templates, assess)
  Stubs only -- no implementation behind any command

Infrastructure:
  pyproject.toml -- Poetry, src layout, ruff/black/mypy/pytest, CalVer
  .claude/hooks/ -- pre-edit-validate.py + post-edit-lint.py
  .github/workflows/ -- ci.yml, release.yml, validate-templates.yml
  templates/ -- manifest.json skeleton, directory structure

Tests: 37 total, all real fakes (no mocks) -- cannot run until poetry install

## Known Issues

- poetry install not run. No virtualenv, no poetry.lock. Tests cannot run yet.
- MCPProbe._check_server() is stubbed (always returns False). Enterprise MCP
  endpoint URLs are unknown -- need Pierre to check Claude Enterprise config.
- knowledge/mastery/ is empty. 206 ServiceNow product docs from JARVIS
  need to be ported or rebuilt. Decision pending.
- Template schemas (templates/schemas/*.py) are stubs. Pydantic models for
  NowAssistSkill and Workflow are the first two to design.
- cli.py commands all raise NotImplementedError. No end-to-end path works yet.

## What's Left

2026.05 -- MVP Commands:
  AnthropicClient.complete() with prompt caching  [active]
  GitHubSync -- manifest fetch + template download
  TemplateRegistry -- list and get from local cache
  InstanceScanner -- health scan via ServiceNowClient
  RuleEngine + AssessmentReporter
  nexus setup command -- credential wizard
  nexus status command -- probe capabilities, verify SN

2026.06 -- Template Library:
  NowAssistSkill + Workflow Pydantic schemas
  First 3+ community templates in templates/
  Template apply engine (ApplyEngine)
  Gate 1 readiness check + Gate 2 validation check

2026.07 -- Agent Specialists:
  8 domain specialist agents implemented
  ExecutionContext enrichment from enterprise MCP
  Multi-step orchestration via Planner + Dispatcher
  Rollback manager for failed deployments

2026.08 -- Distribution:
  100% line coverage, mypy strict, ruff 0 violations
  README + getting started documentation
  PyPI publish (nexus-sn)

Backlog:
  NiceGUI web interface (nexus[ui] optional extra)
  Knowledge mastery KB (206 ServiceNow product docs)
  MCPProbe real endpoint URLs
  JIRA, GitHub, Confluence connectors
