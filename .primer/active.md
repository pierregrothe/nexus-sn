# NEXUS -- Active Work

Last updated: 2026-05-07
Session: Initial scaffolding complete. primer files initialized.

## Current focus

No commits yet. Branch: main (uncommitted).

MVP Step 1 is the immediate next task:
  src/nexus/api/client.py -- implement AnthropicClient.complete() with prompt caching
  tests/fakes/fake_anthropic_client.py -- FakeAnthropicClient
  tests/test_api_client.py -- tests for AnthropicClient

Build order after that (from active.md prior session context):
  Step 2: templates/sync.py -- GitHubSync.fetch_manifest() + download_changed()
  Step 3: templates/registry.py -- TemplateRegistry.list() + get()
  Step 4: assessment/scanner.py -- InstanceScanner using ServiceNowClient
  Step 5: assessment/rules.py + reporter.py -- RuleEngine + AssessmentReporter
  Step 6: nexus setup command -- credential wizard, config write, initial sync
  Step 7: nexus status command -- probe capabilities, verify SN connectivity

## Blockers

- poetry install not run yet -- no poetry.lock, no virtualenv. Run before any test.
- MCPProbe._check_server() returns False (stubbed). Need enterprise MCP endpoint
  URLs from Claude Enterprise account config. Ask Pierre before implementing.
- knowledge/mastery/ is empty. Decision pending: copy from JARVIS or build fresh.

## What was scaffolded (prior session)

Foundation layers (production-ready):
  config/       -- NexusPaths, NexusConfig, ConfigManager
  auth/         -- KeychainClient, ClaudeAuth, SNAuth, AuthError
  capabilities/ -- FeatureFlag, MCPServer, FEATURE_MAP, ProbeResult, CapabilitySet
  connectors/   -- ConnectorProtocol, ToolResult, ConnectorRegistry
  connectors/servicenow/ -- ServiceNowClient, error hierarchy

Stubs (interface defined, no implementation):
  api/           -- AnthropicClient, ToolRegistry
  agents/specialists/* -- 8 domain agent stubs
  knowledge/     -- KnowledgeLoader, ProductIndex
  templates/     -- TemplateRegistry, GitHubSync, ApplyEngine, Validator
  assessment/    -- Scanner, ReadinessChecker, RuleEngine, Reporter
  execution/     -- Planner, Dispatcher, RollbackManager, Reporter

Tests (39 total, all real -- no mocks):
  test_config.py (12), test_auth.py (12), test_capabilities.py (7), test_sn_client.py (8)
