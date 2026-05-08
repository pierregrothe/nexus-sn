# Progress

## What Works

Config layer:
  NexusPaths -- XDG-compliant path resolution (~/.nexus/*, ~/.config/nexus/*)
  NexusConfig -- Pydantic model (frozen) for config.yaml
  ConfigManager -- read/write with env var override support

Auth layer:
  KeychainClient + FakeKeychainClient -- OS keychain via keyring
  ClaudeAuth -- Claude Enterprise API key retrieval (env var or keychain)
  SNAuth -- ServiceNow credentials retrieval
  AuthError hierarchy

Capabilities layer:
  FeatureFlag, MCPServer enums
  FEATURE_MAP -- maps features to required MCP servers
  ProbeResult, CapabilitySet -- startup capability state

Connectors layer:
  ConnectorProtocol -- plugin interface
  ConnectorRegistry -- dynamic connector loading
  ServiceNowClient + FakeServiceNowClient -- REST API
  ServiceNowConnector -- protocol implementation
  Full error hierarchy (SNAuthError, SNNotFoundError, SNRateLimitError, SNClientError)

API layer (Agent SDK migration complete, PR #2 merged 2026-05-08):
  AgentClient -- async wrapper around claude_agent_sdk.query(). Auth handled
                  internally by the SDK (env var > Claude Code stored creds >
                  macOS Keychain). Callers construct AgentClient() and call
                  await client.complete(prompt, system=..., model=..., max_turns=...).
  AgentClientProtocol -- structural interface for agents and CLI commands
  AnthropicError -- typed exception (status_code, message); kept after SDK swap
                    for raising on ResultMessage.is_error from Agent SDK
  configure_logging -- TimedRotatingFileHandler with 7-day rotation, attaches
                       to root logger (file + stderr handlers)
  FakeAgentClient -- @dataclass(slots=True) test double, records calls, returns
                     canned_response or raises side_effect

Agents base:
  AgentProtocol, ExecutionContext, AgentResult

CLI skeleton:
  All 5 MVP commands present in cli.py (setup, status, sync, templates, assess)
  Stubs only -- no implementation behind any command yet
  ui command works end-to-end: imports start_ui (always-importable), calls it,
    raises clean ImportError if nicegui not installed

Governance enforcement:
  Pre-edit hook (.claude/hooks/pre-edit-validate.py) -- blocks anti-patterns
    before file write
  Coverage ratchet (.ratchet.json) -- per-module covered_lines can only increase
  Post-edit checks: ruff + mypy + pyright (all strict, all blocking)
  Lean CI: lint only on every push (<30s), full tests on release tags
  Pre-commit hook: black + ruff + mypy + pyright + pytest (CI-aligned)
  Cross-platform venv resolution (POSIX bin/, Windows Scripts/.exe)

Infrastructure:
  pyproject.toml -- Python 3.14, Poetry in-project venv, ruff/black/mypy/pyright
  pyrightconfig.json -- strict, py314
  .ratchet.json -- coverage baseline for implemented modules
  .pre-commit-config.yaml -- 5 hooks aligned with CI lint stage (semgrep
    addition pending in PR #3)
  .github/workflows/ci.yml -- lean (lint matrix on push, test matrix on tags)

Tests: 45 passing. All real fakes, no mocks.
GitHub: https://github.com/pierregrothe/nexus-sn (public).

## Known Issues

- MCPProbe._check_server() returns False (stub). Enterprise MCP endpoint URLs
  unknown. With Agent SDK as the LLM layer, MCP wiring goes through
  ClaudeAgentOptions(mcp_servers=...); probing strategy needs revisit.
- knowledge/mastery/ empty. Decision pending: copy from JARVIS or rebuild.
- Template schemas (templates/schemas/*.py) are stubs. NowAssistSkill and Workflow
  Pydantic models are the first to design.
- cli.py commands (setup, status, sync, templates, assess) raise NotImplementedError.
- Stub modules at 0% coverage (agents/specialists/*, cli, connectors/servicenow/*,
  templates, assessment, execution, knowledge). Tracked in .ratchet.json once impl
  begins; full 100% gate achieved as stubs implement.
- 8 grandfathered dict[str, Any] usages in src/nexus/connectors/servicenow/client.py.
  Pre-edit hook still blocks new ones; refactor to a typed alias is on the backlog.

## What's Left

2026.05 -- MVP Commands:
  GitHubSync -- manifest fetch + template download (next up)
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
  8 domain specialist agents implemented (each takes AgentClientProtocol)
  ExecutionContext enrichment from enterprise MCP (via Agent SDK mcp_servers)
  Multi-step orchestration via Planner + Dispatcher
  Rollback manager for failed deployments

2026.08 -- Distribution:
  100% line coverage, mypy strict, ruff 0 violations
  README + getting started documentation
  PyPI publish (nexus-sn)

Backlog:
  NiceGUI web interface (nexus[ui] optional extra)
  Knowledge mastery KB (206 ServiceNow product docs)
  MCPProbe with real enterprise MCP endpoints
  JIRA, GitHub, Confluence connectors
  Refactor servicenow/client.py dict[str, Any] -> typed alias
