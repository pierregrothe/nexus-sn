# NEXUS -- Stack

## Runtime

Python 3.14+. All Python 3.14 syntax permitted, including PEP 758 unparenthesized
multi-except, PEP 649 deferred annotation evaluation (default in 3.14), and
PEP 695 type parameter syntax. Earlier 3.12/3.13 are not supported (ADR-006).

## Package manager

Poetry with virtualenvs.in-project = true. Activate once per shell:
`source .venv/bin/activate`. After that, run tools directly: pytest, ruff,
mypy, pyright, black. Hooks invoke .venv/bin/<tool> directly to bypass Poetry
overhead and work regardless of whether the venv is active.

## Layout

src/nexus/      -- Python package (src layout)
  config/       -- Layer 1: settings, paths, config manager
  auth/         -- Layer 2: Claude API key + SN credentials + keychain
  capabilities/ -- Layer 3: MCP probe + feature flags + CapabilitySet
  api/          -- Layer 4a: claude-agent-sdk wrapper (AgentClient async query)
  connectors/   -- Layer 4b: connector plugin system
    servicenow/ -- built-in SN REST connector (replaces MCP server)
  agents/       -- Layer 5a: orchestrator, router, specialist agents
  knowledge/    -- Layer 5b: mastery KB loader and product index
  templates/    -- Layer 5c: registry, sync, apply, validator + schemas
  assessment/   -- Layer 5d: scanner, readiness, validator, reporter
  execution/    -- Layer 5e: planner, dispatcher, rollback, reporter
  cli.py        -- Layer 6: Typer entry point
  ui/           -- Layer 7: CLI component library + NiceGUI (optional)
    components/ -- StatusBadge, KeyValuePanel, DataTable, CommandGuide,
                   Hint, Notice, default_marker, nexus_progress

tests/
  fakes/        -- FakeServiceNowClient, FakeKeychainClient,
                   FakeAgentClient (NO MOCKS EVER)
  test_*.py     -- test files

templates/      -- community YAML template library (GitHub root)
  manifest.json, workflows/, ai-agents/, now-assist-skills/, catalog-items/,
  business-rules/, projects/, recipes/, assessments/{health,readiness,validation}/

## Core dependencies

claude-agent-sdk >= 0.1   -- LLM access; wraps bundled Claude Code CLI as
                              subprocess; auth via env var, stored creds, or
                              macOS Keychain (ADR-015)
httpx >= 0.28             -- async SN REST client
pydantic >= 2.9           -- models everywhere (frozen=True, strict=True, extra="forbid")
pydantic-settings >= 2.6  -- config from env + YAML
typer[all] >= 0.13        -- CLI framework
rich >= 13.9              -- terminal output
keyring >= 25             -- OS keychain for secrets
pyyaml >= 6.0             -- template parsing

## Optional dependency

nicegui >= 2.0  -- web dashboard (pip install nexus-sn[ui])

## Dev tools

pytest >= 9.0 + pytest-asyncio + pytest-cov
mypy >= 1.0 (strict mode, 0 errors required)
pyright >= 1.1 (strict mode, 0 errors required) -- ADR-012
ruff >= 0.15 (0 violations required)
black >= 26.3 (line length 100)
pre-commit >= 4.0

## Tooling config (pyproject.toml)

[tool.ruff] target-version = "py314", line-length = 100
[tool.black] target-version = ["py314"], line-length = 100
[tool.mypy] python_version = "3.14", strict = true,
  warn_return_any = true, warn_unused_ignores = true, strict_equality = true
ban-relative-imports = "all"
banned: unittest.mock, pytest_mock (use fakes)
pytest asyncio_mode = "auto", pythonpath = ["src"]
coverage fail-under = 100

[pyrightconfig.json] pythonVersion = "3.14", typeCheckingMode = "strict"

## Claude Code hooks (3-tier enforcement, ADR-011)

Tier 1 -- Blocking (PreToolUse: pre-edit-validate.py): 10 rules
  mocks, relative imports, bare except, lru_cache(maxsize=None), unittest.TestCase,
  sys.argv (non-test), # type: ignore (ADR-007), bare Any in signatures (ADR-008),
  dict[str, Any] in signatures (ADR-008), deferred imports (TYPE_CHECKING exempt)

Tier 2 -- Ratchet (PostToolUse: post-edit-lint.py): coverage-ratchet
  Per-module covered_lines tracked in .ratchet.json, can only increase

Tier 3 -- Soft (planned): missing-test-file, unclosed-resource-handle

Post-edit also runs: ruff + mypy + pyright on the edited file (blocking)

## CI (GitHub Actions, ADR-013)

ci.yml             -- on every push: black + ruff + mypy + pyright (lint stage <30s)
                      on release tags: full pytest matrix (ubuntu/macos/windows)
release.yml        -- build wheel + publish to PyPI on CalVer tag
validate-templates.yml -- validate changed YAML on PR touching templates/

## Pre-commit (local, before every commit)

.pre-commit-config.yaml: black + ruff + mypy + pyright + pytest
Aligned with CI lint stage; a commit that passes pre-commit will pass CI.

## Versioning

CalVer: YYYY.0M.PATCH (e.g. 2026.05.1)
CHANGELOG.md entry required for every release.

## Secrets

OS keychain (keyring) for:
  - Claude Enterprise API key: service="nexus-claude", username="api_key"
  - SN password per profile: service="nexus-sn-<profile>", username=<username>
Env var overrides for CI:
  NEXUS_CLAUDE_API_KEY, NEXUS_SN_PASSWORD_<PROFILE>
Never in config files. Never logged.

## Config file

~/.nexus/config.yaml -- no secrets, only references and preferences
~/.nexus/templates/  -- local template cache (nexus sync populates this)
~/.nexus/reports/    -- generated HTML reports
~/.nexus/jobs/       -- job history, rollback manifests
~/.nexus/logs/       -- rotating session logs (7 days, configure_logging)

## LLM access

AgentClient (src/nexus/api/agent_client.py) wraps claude_agent_sdk.query() with
a simple async interface:
  async def complete(self, prompt: str, *, system: str | None = None,
                     model: str | None = None, max_turns: int = 1) -> str
Auth is handled internally by claude-agent-sdk:
  ANTHROPIC_API_KEY env > CLAUDE_CODE_OAUTH_TOKEN env >
  $CLAUDE_CONFIG_DIR/.credentials.json (or ~/.claude/.credentials.json) >
  macOS Keychain "Claude Code-credentials".
Each query() call spawns the bundled Claude Code CLI as a subprocess; cold
calls run SessionStart hooks (~10-30s). Subsequent calls within the same
process reuse cached state. Model selection is delegated to the SDK; pass a
specific model string only when overriding the default.
