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
  ServiceNowClient + FakeServiceNowClient -- REST API
  ServiceNowConnector -- protocol implementation
  Full error hierarchy (SNAuthError, SNNotFoundError, SNRateLimitError, SNClientError)

API layer (MVP Step 1 complete):
  AnthropicClient -- Anthropic SDK wrapper with prompt caching, cache-hit logging,
                     and error mapping (AuthError, AnthropicError). Takes a
                     Sequence[AuthProvider] and resolves first available at init.
  AnthropicClientProtocol -- structural interface for agents and CLI commands
  ModelTier (StrEnum) -- STANDARD/POWERFUL/FAST tiers, auto-discovered at init
                          via client.models.list() with created_at sort, env var
                          override (NEXUS_MODEL_*), hardcoded fallback
  AnthropicError -- typed exception with status_code and message
  ToolRegistry -- assembles connector tools as anthropic.types.ToolParam list
  configure_logging -- TimedRotatingFileHandler with 7-day rotation, attaches
                       to root logger (file + stderr handlers)
  FakeAnthropicClient -- test double, records calls, returns CANNED_MESSAGE

Auth layer extended (NEW -- pluggable provider system, PR #1):
  AuthProvider (Protocol) -- name property, is_available, create_client(max_retries)
  ClaudeCodeOAuthProvider -- reads OAuth token from CLAUDE_CODE_OAUTH_TOKEN env,
                              ~/.claude/.credentials.json, or macOS Keychain
                              ("Claude Code-credentials" via keyring lib).
                              Per-instance cache; first source wins.
  AnthropicAPIKeyProvider -- ClaudeAuth alias; reads NEXUS_CLAUDE_API_KEY env
                              or nexus keychain entry. Cached after resolution.
  get_default_providers() -- returns [OAuth, APIKey] in priority order.
  FakeAuthProvider -- test double for AuthProvider Protocol.

Agents base:
  AgentProtocol, ExecutionContext, AgentResult

CLI skeleton:
  All 5 MVP commands present in cli.py (setup, status, sync, templates, assess)
  Stubs only -- no implementation behind any command yet
  ui command works end-to-end: imports start_ui (always-importable), calls it,
    raises clean ImportError if nicegui not installed

Governance enforcement (NEW -- ADRs 006-013):
  10 blocking pre-edit rules: no-mocks, no-relative-imports, no-bare-except,
    no-lru-cache-none, no-unittest-testcase, no-sys-argv, no-type-ignore,
    no-bare-any-in-sig, no-dict-any-in-sig, no-deferred-import
  Coverage ratchet (.ratchet.json) -- per-module covered_lines can only increase
  Post-edit checks: ruff + mypy + pyright (all strict, all blocking)
  Lean CI: lint only on every push (<30s), full tests on release tags
  Pre-commit hook: black + ruff + mypy + pyright + pytest (CI-aligned)
  Cross-platform venv resolution (POSIX bin/, Windows Scripts/.exe)

Infrastructure:
  pyproject.toml -- Python 3.14, Poetry in-project venv, ruff/black/mypy/pyright
  pyrightconfig.json -- strict, py314
  .ratchet.json -- coverage baseline for 16 implemented modules
  .pre-commit-config.yaml -- 5 hooks aligned with CI lint stage
  .github/workflows/ci.yml -- lean (lint matrix on push, test matrix on tags)

Tests: 71 passing (53 prior + 18 new for AuthProvider system). All real fakes, no mocks.
GitHub: https://github.com/pierregrothe/nexus-sn (public, governance-baseline-2026-05-07 tag).

## Known Issues

- MCPProbe._check_server() returns False (stub). Enterprise MCP endpoint URLs
  unknown -- needs inspection of Claude Enterprise config.
- knowledge/mastery/ empty. Decision pending: copy from JARVIS or rebuild.
- Template schemas (templates/schemas/*.py) are stubs. NowAssistSkill and Workflow
  Pydantic models are the first to design.
- cli.py commands (setup, status, sync, templates, assess) raise NotImplementedError.
- Stub modules at 0% coverage (agents/specialists/*, cli, connectors/servicenow/*,
  templates, assessment, execution, knowledge). Tracked in .ratchet.json once impl
  begins; full 100% gate achieved as stubs implement.

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
