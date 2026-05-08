# Progress

## What Works

Config layer:
  NexusPaths -- XDG-compliant path resolution (~/.nexus/*, ~/.config/nexus/*)
  NexusConfig -- Pydantic model (frozen) for config.yaml
  ConfigManager -- read/write with env var override support

Auth layer:
  KeychainClient + FakeKeychainClient -- OS keychain via keyring
  ExternalKeychainClient -- cross-app keychain reads (e.g., Claude Code credentials)
  ClaudeAuth -- Claude Enterprise API key retrieval (env var or keychain)
  SNAuth -- ServiceNow credentials retrieval
  AuthError hierarchy

Capabilities layer:
  FeatureFlag, MCPServer enums
  FEATURE_MAP -- maps features to required MCP servers
  ProbeResult, CapabilitySet -- startup capability state
  TierDetector + Tier enum -- detects enterprise/pro/free from Claude Code OAuth
    signals (subscription claim, mcpEverConnected list, needs-auth cache file)
  ClaudeCodeConfig dataclass -- reads ~/.claude.json: email, org name, subscription
    type, detected MCP servers (oauthAccount + claudeAiMcpEverConnected)

Connectors layer:
  ConnectorProtocol -- plugin interface
  ConnectorRegistry -- dynamic connector loading
  ServiceNowClient + FakeServiceNowClient -- REST API
  ServiceNowConnector -- protocol implementation
  Full error hierarchy (SNAuthError, SNNotFoundError, SNRateLimitError, SNClientError)

API layer:
  AgentClient -- async wrapper around claude_agent_sdk.query(). Auth handled
    internally by the SDK (env var > Claude Code stored creds > macOS Keychain).
  AgentClientProtocol -- structural interface for agents and CLI commands
  AnthropicError -- typed exception (status_code, message)
  configure_logging -- TimedRotatingFileHandler with 7-day rotation
  FakeAgentClient -- @dataclass(slots=True) test double

Caching layer:
  @cached(ttl, persist, namespace, key_fn) -- canonical caching decorator
  CacheBackend -- in-memory (default) + disk (diskcache, persist=True)
  clear_cache(target) -- invalidation utility

Updater layer:
  UpdateChecker -- GitHub Releases API, 24h TTL check
  WheelDownloader -- downloads wheel from release assets
  Installer + Runner -- pip install + os.execv re-exec on update
  NEXUS_AUTO_UPDATE=0 escape hatch; editable installs skip silently

UI layer:
  NEXUS_THEME + themed Console -- ServiceNow brand colors
  GradientPanel -- Rich renderable with left-to-right RGB gradient border;
    supports title, padding, min_height for equal-height column pairs
  gradient_text() -- per-character RGB gradient coloring for value strings
  SN_BLUE, SN_LIME, SN_TEXT_START -- ServiceNow brand gradient stops
  banner_text() / print_banner() -- SN_BLUE->SN_LIME gradient NEXUS ASCII art
  StatusReporter -- 3-row dashboard:
    Row 1: Identity (user, org, tier, version, servers) | System (python, platform, install)
    Row 2: Integrations (dynamic; only detected MCP servers shown)
    Row 3: Diagnostics (config root, cache size) | Auto-update (enabled, last check)

Agents base:
  AgentProtocol, ExecutionContext, AgentResult

CLI:
  nexus status -- fully implemented (banner + tier detection + StatusReporter)
  nexus reauth -- prints one-shot command for servers needing re-auth
  nexus --refresh -- clears cached tier detection
  setup, sync, templates, assess -- stubs (raise NotImplementedError)
  ui command -- clean ImportError if nicegui not installed

Governance enforcement:
  Pre-edit hook (.claude/hooks/pre-edit-validate.py) -- 10 blocking rules
  Coverage ratchet (.ratchet.json) -- per-module covered_lines can only increase
  Semgrep rules (.semgrep/rules.yml) -- semantic rules with ADR tracing
  Post-edit checks: ruff + mypy + pyright (all strict, all blocking)
  Pre-commit hook: black + ruff + mypy + pyright + semgrep + pytest

Infrastructure:
  pyproject.toml -- Python 3.14, Poetry in-project venv, ruff/black/mypy/pyright
  pyrightconfig.json -- strict, py314
  .ratchet.json -- coverage baseline for all implemented modules
  .github/workflows/ci.yml + release.yml -- lean CI + GitHub Releases auto-update

Tests: 219 passing. All real fakes, no mocks.
GitHub: https://github.com/pierregrothe/nexus-sn (public).

## Known Issues

- MCPProbe._check_server() returns False (stub). Enterprise MCP endpoint URLs
  unknown. With Agent SDK as the LLM layer, MCP wiring goes through
  ClaudeAgentOptions(mcp_servers=...); probing strategy needs revisit.
- knowledge/mastery/ empty. Decision pending: copy from JARVIS or rebuild.
- Template schemas (templates/schemas/*.py) are stubs. NowAssistSkill and Workflow
  Pydantic models are the first to design.
- setup, sync, templates, assess commands raise NotImplementedError.
- Stub modules at 0% coverage (agents/specialists/*, connectors/servicenow/*,
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
