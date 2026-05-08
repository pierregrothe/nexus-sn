# NEXUS -- Active Work

Last updated: 2026-05-08
Session: Agent SDK migration shipped (PR #2), governance refactor in flight (PR #3).

## Current focus

Two recent landings on main:

  PR #2 (merged 2026-05-08, commit 477c4b3) -- Migrate from anthropic SDK to
  claude-agent-sdk. Empirical testing showed the OAuth path through the
  standard anthropic SDK is policy-gated at /v1/messages (returns 429 on
  every call). claude-agent-sdk wraps the bundled Claude Code CLI as a
  subprocess and authenticates using the user's stored credentials.

  PR #3 (open, branch chore/semgrep-governance) -- Introduce semgrep for
  semantic governance. Splits the 10-rule custom pre-edit hook into three
  buckets: 5 ruff rules, 2 semgrep rules, 3 file-aware rules in the custom
  hook. ADR-016.

After PR #3 merges, focus returns to MVP build order:

  Step 2: src/nexus/templates/sync.py -- GitHubSync.fetch_manifest() +
          download_changed(). Test with tmp_path and a fake manifest fixture.
  Step 3: templates/registry.py -- TemplateRegistry.list() + get()
  Step 4: assessment/scanner.py -- InstanceScanner using ServiceNowClient
  Step 5: assessment/rules.py + reporter.py -- RuleEngine + AssessmentReporter
  Step 6: nexus setup command -- credential wizard, config write, initial sync
  Step 7: nexus status command -- probe capabilities, verify SN connectivity

## What was completed in the recent sessions

Agent SDK migration (8-task plan, 9 commits squashed to 477c4b3):
  src/nexus/api/agent_client.py -- AgentClient + AgentClientProtocol wrapping
                                    claude_agent_sdk.query()
  tests/fakes/fake_agent_client.py -- FakeAgentClient test double
  tests/test_agent_client.py -- 6 tests
  scripts/smoke_agent.py -- replaces scripts/smoke_anthropic.py
  Deleted: src/nexus/api/client.py (AnthropicClient, ModelTier, _ModelDiscoveryClient),
           src/nexus/api/tool_registry.py, src/nexus/auth/oauth.py,
           src/nexus/auth/providers.py, tests/fakes/fake_anthropic_client.py,
           tests/fakes/fake_auth_provider.py, tests/test_api_client.py,
           tests/test_auth_providers.py, scripts/smoke_anthropic.py
  Reverted: src/nexus/auth/claude.py to pre-PR-#1 shape (no AuthProvider Protocol)
  Dropped: anthropic dep from pyproject.toml
  Net: ~250 lines added, ~1300 lines removed; 71 -> 45 tests
  Smoke test passed end-to-end: 2 calls returned real assistant text via OAuth
  alone, no API key.

Semgrep governance refactor (PR #3, in review):
  .semgrep/rules.yml -- 2 semantic rules with metadata.adr links
  .semgrepignore -- replaces semgrep defaults to scan tests/
  Pre-commit hook adds semgrep via additional_dependencies (isolated venv,
  no project lockfile pollution)
  Custom hook trimmed from 10 checks to 3 file-aware checks
  Ruff selects expanded with PLC0415 + PGH003

## Blockers / open questions

- MCPProbe._check_server() still stubbed (returns False). Real enterprise MCP
  endpoint URLs unknown. With Agent SDK as the LLM layer, MCP probing strategy
  will change -- the SDK exposes MCP via ClaudeAgentOptions(mcp_servers=...);
  separate enterprise MCP probing from the LLM connection.
- knowledge/mastery/ empty. Decision pending: copy from JARVIS or build fresh.
- 8 grandfathered dict[str, Any] usages in src/nexus/connectors/servicenow/client.py
  -- the pre-edit hook still blocks new ones; semgrep rule deferred until those
  are refactored to a typed alias.

## Branch / remote state

main: 477c4b3 (Agent SDK migration merged)
chore/semgrep-governance: open as PR #3, CI green, awaiting merge
After PR #3 merges: branch from main and start MVP Step 2 (GitHubSync).
