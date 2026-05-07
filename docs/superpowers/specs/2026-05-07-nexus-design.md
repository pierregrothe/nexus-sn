# NEXUS Design Specification
# 2026-05-07

## Overview

NEXUS is a standalone Python CLI tool that acts as a ServiceNow AI architect agent.
It uses the Anthropic API directly -- no dependency on Claude Code or Claude Desktop.
It is distributed via public GitHub and PyPI, targets internal ServiceNow colleagues,
and is designed to run identically on Windows, macOS, and Linux.

---

## Core Concept

NEXUS is a ServiceNow configuration package manager backed by AI orchestration.

Two things make it distinct from JARVIS:

1. Templates are declarative YAML artifacts versioned in the GitHub repo.
   The local tool syncs against the registry, validates against Pydantic schemas,
   and applies templates through an AI-assisted execution engine. Templates are
   not prompt fragments -- they are typed, versioned, and testable.

2. The tool leverages ServiceNow enterprise MCP servers (Value Melody, SSC, BT1,
   Data Analytics, GTM, M365) that are available through the Claude Enterprise API
   account. At startup, NEXUS probes each known MCP server and builds a CapabilitySet.
   Features that require unavailable servers are disabled transparently.

---

## Architecture

### Layers (bottom to top)

```
Layer 1  config/        Pydantic settings, ~/.nexus/config.yaml, path constants
Layer 2  auth/          Claude Enterprise API key + SN credentials in OS keychain
Layer 3  capabilities/  MCP server probe at startup -> CapabilitySet + feature flags
Layer 4a api/           Anthropic SDK wrapper with prompt caching + tool registry
Layer 4b connectors/    ServiceNow REST client (the one connector NEXUS owns directly)
Layer 5  agents/        Orchestrator, intent router, specialist agents (Python classes)
         knowledge/     Mastery KB loader and product index
         templates/     Registry, GitHub sync, apply engine, YAML validator
         assessment/    Health scanner, readiness gate, post-deploy validator, reporter
         execution/     Phase 1 planner + Phase 2 parallel dispatcher + rollback
Layer 6  cli.py         Typer entry point
Layer 7  ui/            NiceGUI dashboard (optional -- nexus[ui])
```

Each layer depends only on layers below it. The UI and CLI are independent consumers
of the same Python API surface. Tests cover the layers directly, not through the CLI.

---

## Module Specifications

### config/

settings.py    -- NexusConfig (Pydantic BaseSettings, frozen=True). Reads
                  ~/.nexus/config.yaml. No secrets in the file -- keychain references only.
manager.py     -- ConfigManager: read, write, migrate config across versions.
                  Migration is additive-only. Never deletes existing keys.
paths.py       -- NexusPaths: all ~/.nexus/* path constants as Path objects.
                  One authoritative location for every path NEXUS touches.

Config file schema:
  version: str                    -- config format version for migration
  auth.claude_org: str            -- org slug for keychain lookup
  instances.default: str          -- default instance profile name
  instances.profiles: dict        -- per-instance url + username (password in keychain)
  capabilities.auto_probe: bool   -- probe MCP servers at startup
  capabilities.probe_timeout: int -- seconds before marking a server unavailable
  capabilities.disabled_servers: list[str]  -- manual overrides
  preferences.output_format: str  -- "rich" | "plain" | "json"
  preferences.github_repo: str    -- template registry repo
  preferences.github_branch: str  -- default "main"

### auth/

keychain.py    -- KeychainClient wraps keyring. Single abstraction for get/set/delete.
                  Raises AuthError (not KeyError) on missing credentials.
claude.py      -- ClaudeAuth: store, retrieve, validate Claude Enterprise API key.
                  Validation is a lightweight /models probe against the API.
servicenow.py  -- SNAuth: store, retrieve, rotate SN instance credentials per profile.

No plaintext secrets anywhere. .env.example lists env var overrides for CI.

### capabilities/

probe.py       -- MCPProbe: probes each known SN enterprise MCP server.
                  Uses a 5-second timeout. Records latency + availability.
feature_flags.py -- FEATURE_MAP: dict mapping MCP server names to feature flag names.
                    Known servers: value_melody, ssc, bt1, data_analytics, gtm, m365.
registry.py    -- CapabilitySet (frozen dataclass): snapshot of what is live in
                  this session. Passed to the Anthropic client at init. Drives CLI
                  feature visibility -- unavailable features are hidden, not errored.

Startup sequence:
  1. Load config from ~/.nexus/config.yaml
  2. Retrieve API key from keychain
  3. Probe MCP servers (parallel, 5s timeout each)
  4. Build CapabilitySet
  5. Log one INFO line per server: available / unavailable

### api/

client.py      -- AnthropicClient wraps anthropic.Anthropic. Enables prompt caching
                  on every call. Injects MCP server configs from CapabilitySet into
                  the tools list. Handles retries with exponential backoff (3 attempts).
tool_registry.py -- ToolRegistry: maps tool names to Python callables. Core SN tools
                    are always registered. MCP server tools are added when the server
                    is available. Tools are typed Pydantic models.

### connectors/

base.py        -- ConnectorProtocol (Protocol class). Every connector implements:
                  tools() -> list[Tool]
                  call(tool_name, **kwargs) -> ToolResult
registry.py    -- ConnectorRegistry: discovers + loads enabled connectors.
servicenow/    -- ServiceNow REST connector. Always present.
  client.py    -- async httpx client. Connection pool, retry, rate limiting.
  auth.py      -- basic auth, OAuth, SSO handlers.
  tools.py     -- 80+ SN operations as typed async functions.
  schemas.py   -- Pydantic models for SN record types (Incident, CI, Flow, etc.)

### agents/

base.py        -- AgentProtocol (Protocol). Every specialist implements:
                  name: str
                  domain: str
                  run(context: ExecutionContext) -> AgentResult
orchestrator.py -- MasterOrchestrator: coordinates all specialists. Owns the
                   two-phase execution loop (plan -> dispatch).
router.py      -- IntentRouter: classifies a user request to one or more domain
                   agents. Uses the Anthropic API for classification (not keyword
                   matching). Returns a list of required agents with confidence scores.
context.py     -- ExecutionContext: immutable snapshot passed to each agent.
                   AgentResult: typed output (created sys_ids, errors, next steps).

specialists/   -- One file per domain. Each is a concrete AgentProtocol implementation.
  itsm.py      -- ITSMAgent (incident, problem, change, request, knowledge, SLA)
  itom.py      -- ITOMAgent (events, discovery, service mapping, AIOps)
  hrsd.py      -- HRSDAgent (HR cases, employee center, lifecycle events)
  csm.py       -- CSMAgent (customer cases, field service, orders)
  irm.py       -- IRMAgent (risk, compliance, audit, vendor risk)
  secops.py    -- SecOpsAgent (SIR, vulnerability, threat intel, SOAR)
  spm.py       -- SPMAgent (PPM, demand, resource, agile)
  platform.py  -- PlatformAgent (platform config, scripting, integrations)

### knowledge/

loader.py      -- KnowledgeLoader: loads mastery markdown files from the bundled
                  knowledge/ directory. Caches content with @cache. Provides
                  get_product_doc(product_name) -> str.
index.py       -- ProductIndex: maps product names and aliases to mastery doc paths.
                  Built from index.json at package time.
mastery/       -- Markdown files (one per product). Bundled in the wheel.
                  Not generated at runtime -- committed to the repo and shipped.

### templates/

registry.py    -- TemplateRegistry: discovers templates in the local cache
                  (~/.nexus/templates/). Returns typed TemplateManifest objects.
sync.py        -- GitHubSync: fetches manifest.json from the configured GitHub repo,
                  downloads changed templates to ~/.nexus/templates/. Uses ETags for
                  conditional requests. Respects rate limits.
apply.py       -- TemplateApplyEngine: reads a template, resolves its dependencies,
                  passes it to the execution engine as a structured plan.
validator.py   -- TemplateValidator: validates YAML against the appropriate Pydantic
                  schema before any apply. Hard-fails on schema violations.
schemas/       -- One Pydantic model per template type.
  workflow.py      -- WorkflowTemplate
  ai_agent.py      -- AIAgentTemplate
  now_assist_skill.py -- NowAssistSkillTemplate
  catalog_item.py  -- CatalogItemTemplate
  recipe.py        -- RecipeTemplate (low-level SN config)
  project.py       -- ProjectTemplate (high-level blueprint referencing other templates)

### assessment/

scanner.py     -- InstanceScanner: queries a live SN instance and collects state.
                  Saves scan results to ~/.nexus/jobs/<timestamp>/scan.json.
readiness.py   -- ReadinessChecker: evaluates a template's requirements against
                  instance state. Returns ReadinessReport (pass/fail per check).
validator.py   -- DeploymentValidator: post-deploy validation. Reads the job's
                  execution record and verifies all expected records exist.
rules.py       -- RuleEngine: loads YAML ruleset files from templates/assessments/.
                  Evaluates rules against instance state. Returns RuleResult per rule.
reporter.py    -- AssessmentReporter: generates HTML + JSON reports. Saves to
                  ~/.nexus/reports/<timestamp>-<type>.html.
schemas/
  health.py        -- HealthReport
  readiness.py     -- ReadinessReport
  validation.py    -- ValidationReport

### execution/

planner.py     -- Phase1Planner: produces a TaskManifest from a user request or
                  template. Calls ReadinessChecker. Generates rollback plan.
                  Generates HTML executive briefing. Pauses for user approval.
dispatcher.py  -- Phase2Dispatcher: executes the TaskManifest. Tracks task status
                  with a dependency graph. Dispatches agents in parallel when
                  dependencies resolve. Passes ExecutionContext between tasks.
rollback.py    -- RollbackManager: generates GlideRecord deletion scripts ordered
                  by FK constraints. Executes rollback on demand.
reporter.py    -- ExecutionReporter: generates the final HTML deployment report.
                  Saves to ~/.nexus/reports/.

### cli.py

Typer application. All commands validate config and credentials before running.
Unavailable features are hidden from help text (not shown as errors).

Commands:
  nexus setup                       -- first-run wizard: credentials, config, sync
  nexus sync                        -- pull latest templates from GitHub
  nexus templates list              -- browse available templates
  nexus templates info <name>       -- show template schema and requirements
  nexus apply <template>            -- deploy with readiness gate + validation
  nexus run "<request>"             -- free-form AI orchestration
  nexus assess                      -- standalone health scan
  nexus assess --for <template>     -- readiness check only
  nexus assess --job <id>           -- validate a past deployment
  nexus rollback <job-id>           -- undo a deployment
  nexus status                      -- instance connection + capability summary
  nexus ui                          -- start NiceGUI dashboard (nexus[ui] required)

### ui/

__init__.py    -- Guards: raises ImportError with install instructions if nicegui
                  is not installed.
app.py         -- NiceGUI application stub. Exposes the same Python API as the CLI.
                  Phase 2 implementation -- not in MVP.

---

## Template System

Templates live in two places:

1. `templates/` at the GitHub repo root -- the community registry. This is the
   source of truth. CI validates every template YAML on PR before merge.

2. `~/.nexus/templates/` -- the local cache populated by `nexus sync`.

Template types (each has a Pydantic schema in nexus/templates/schemas/):

  workflow           -- Flow Designer flows and subflows
  ai-agent           -- SN AI Agent Studio agents
  now-assist-skill   -- Now Assist skill definitions
  catalog-item       -- Service catalog items
  business-rule      -- Business rules
  recipe             -- Low-level SN configuration (any table, any record)
  project            -- High-level blueprint referencing multiple templates
  assessment/health  -- Health scan ruleset
  assessment/readiness -- Pre-deploy readiness ruleset
  assessment/validation -- Post-deploy validation ruleset

Template YAML structure (minimum):
  name: str
  version: str       -- semver (e.g. 1.2.0)
  type: str          -- one of the types above
  sn_version: str    -- minimum SN release (e.g. ">=Xanadu")
  requires: list     -- plugins, license tier, other templates
  spec: dict         -- type-specific configuration
  tests: list        -- scenario-based validation cases

manifest.json at the repo root lists all available templates with name, type,
version, path, and checksum. NEXUS downloads only changed files on sync.

---

## Authentication and Configuration Persistence

Claude Enterprise API key:
  - Stored in OS keychain under service="nexus", username="claude_api_key"
  - Retrieved at startup, never logged
  - Validated with a lightweight /models probe
  - Set via: nexus setup or NEXUS_CLAUDE_API_KEY env var (CI use)

ServiceNow credentials (per profile):
  - URL stored in config.yaml (not sensitive)
  - Username stored in config.yaml (not sensitive)
  - Password stored in keychain: service="nexus-sn-<profile>", username=<username>
  - Set via: nexus setup or NEXUS_SN_PASSWORD_<PROFILE> env var (CI use)

Config file: ~/.nexus/config.yaml
  - No secrets. Keychain references only.
  - Safe to commit to personal dotfiles.
  - Migrated automatically on version upgrade via ConfigManager.

Job history: ~/.nexus/jobs/<timestamp>-<template>/
  - scan.json     -- pre-deploy instance state
  - manifest.json -- task manifest
  - rollback.json -- rollback scripts
  - result.json   -- execution result

---

## MCP Capability Detection

Known ServiceNow enterprise MCP servers probed at startup:

  value_melody    -- Value Melody: ROI, VE pipeline, value calculations
  ssc             -- Sales Success Center: content, competitive intel, battle cards
  bt1             -- BT1: internal work item tracking, project data
  data_analytics  -- Snowflake analytics: account insights, customer data
  gtm             -- GTM: deal registration, partner data
  m365            -- Microsoft 365: email, calendar, SharePoint

Probe: lightweight tool-list call with 5-second timeout.
Result: CapabilitySet (frozen dataclass) listing available + unavailable servers.
Effect: CLI commands that require an unavailable server are hidden from --help.
        Agents that require an unavailable server log a WARNING and skip that step.

---

## Error Handling

NexusError hierarchy:
  NexusError          -- base
    ConfigError       -- missing or invalid config
    AuthError         -- credential lookup failed
    SNClientError     -- ServiceNow API error
      SNAuthError     -- 401/403
      SNNotFoundError -- 404
      SNRateLimitError -- 429
    TemplateError     -- invalid template YAML
      SchemaError     -- Pydantic validation failure
      VersionError    -- SN version incompatibility
    AssessmentError   -- readiness gate failure
    ExecutionError    -- agent or dispatch failure

Exit codes (CLI):
  0  success
  1  blocking error (bad credentials, gate failure, validation failure)
  2  usage error (bad arguments, unknown template)

Errors are printed to stderr. Machine-readable output goes to stdout.
Structured errors include: code (snake_case), message, suggestion, blocking flag.

---

## Testing Standards (from skills-dev)

- No mocks. unittest.mock, MagicMock, monkeypatch are blocked by pre-edit hook.
- Use fakes: tests/fakes/fake_sn_client.py, tests/fakes/fake_anthropic_client.py.
- 100% line coverage on all nexus/ modules.
- mypy strict: 0 errors.
- ruff: 0 violations.
- black: compliant.
- Test naming: test_<function>_<scenario>.
- All test functions have complete type annotations.
- Use tmp_path for all file I/O.
- Test happy path and all error/fallback branches.

---

## Toolchain (from skills-dev)

Package manager: Poetry
Python: >=3.12
Line length: 100
Versioning: CalVer (YYYY.0M.PATCH) -- e.g. 2026.05.1

Hooks (Claude Code):
  PreToolUse:  pre-edit-validate.py -- blocks mocks, bare except, relative imports,
               sys.argv indexing, @lru_cache(maxsize=None), unittest.TestCase
  PostToolUse: post-edit-lint.py    -- runs ruff + mypy after every Python edit
  SessionStart: audit-session.py   -- loads project rules into context

---

## Dependencies

Core (pip install nexus-sn):
  anthropic >= 0.50
  httpx >= 0.28        -- async SN REST client
  pydantic >= 2.9
  pydantic-settings >= 2.6
  typer[all] >= 0.13
  rich >= 13.9
  keyring >= 25        -- OS keychain
  pyyaml >= 6.0        -- template parsing

Optional (pip install nexus-sn[ui]):
  nicegui >= 2.0

Dev:
  pytest >= 9.0
  pytest-asyncio >= 0.24
  pytest-cov >= 7.0
  mypy >= 1.0
  ruff >= 0.15
  black >= 26.3
  pre-commit >= 4.0

---

## Distribution

GitHub: public repo at github.com/<org>/nexus-sn
PyPI:   nexus-sn package
Install: pip install nexus-sn  (or pip install nexus-sn[ui] for the dashboard)

GitHub Actions:
  ci.yml                -- runs on every PR: pytest, ruff, mypy, black --check
  release.yml           -- triggered on version tag: builds wheel, publishes to PyPI
  validate-templates.yml -- runs on PR touching templates/: validates YAML schemas

---

## MVP Scope

The MVP delivers a working CLI that can:
1. Run nexus setup (configure credentials and sync templates)
2. Run nexus status (verify connections and show CapabilitySet)
3. Run nexus sync (pull templates from GitHub)
4. Run nexus templates list (browse available templates)
5. Run nexus assess (health scan of an SN instance)

The orchestration engine (nexus run, nexus apply) and specialist agents are
stubbed in the MVP with correct interfaces but no implementation. This validates
the architecture and gives colleagues something to install immediately.

---

## Files Excluded from MVP (stubbed only)

- nexus/agents/specialists/* (interfaces defined, no implementation)
- nexus/execution/* (interfaces defined, no implementation)
- nexus/ui/* (ImportError guard only)
- templates/* (empty directories with README.md only)
