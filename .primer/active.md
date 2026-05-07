# NEXUS -- Active Work

Last updated: 2026-05-07
Session: MVP Step 1 complete + sprint retrospective + governance enforcement Plans 1 & 2.

## Current focus

MVP Step 1 (AnthropicClient) is DONE. Next is Step 2: GitHubSync.

  src/nexus/templates/sync.py -- implement GitHubSync.fetch_manifest() + download_changed()
  Test with tmp_path and a fake manifest fixture.

Build order from here (rest of 2026.05 milestone):
  Step 3: templates/registry.py -- TemplateRegistry.list() + get()
  Step 4: assessment/scanner.py -- InstanceScanner using ServiceNowClient
  Step 5: assessment/rules.py + reporter.py -- RuleEngine + AssessmentReporter
  Step 6: nexus setup command -- credential wizard, config write, initial sync
  Step 7: nexus status command -- probe capabilities, verify SN connectivity

## What was completed this session

MVP Step 1 -- AnthropicClient (commits c28af22 -> 1cd5bbb, 13 commits):
  api/client.py -- ModelTier auto-discovery via models.list(), prompt caching,
                   error mapping (AuthError, AnthropicError), cache-hit logging
  api/errors.py -- AnthropicError(status_code, message)
  api/logging_config.py -- TimedRotatingFileHandler with 7-day rotation
  api/__init__.py -- exports AnthropicClient, AnthropicClientProtocol, ModelTier,
                     AnthropicError, ToolRegistry, configure_logging
  tests/fakes/fake_anthropic_client.py -- FakeAnthropicClient with MessageParam/ToolParam
  tests/test_api_client.py -- 14 tests covering all behaviors

Governance enforcement (Plan 1 + Plan 2, 16 commits):
  Hook fixes: shell expansion, stderr routing, .venv/bin direct invocation
  Python 3.14 minimum (pyproject + pyrightconfig + CLAUDE.md)
  Pyright strict added alongside mypy
  4 new pre-edit blocking rules: type-ignore-ban, bare-any-in-sig,
                                  dict-any-in-sig, deferred-import-in-body
  Coverage ratchet (.ratchet.json) with per-module gate (scoped to edited module)
  Lean CI (lint only on push, tests on release tags)
  Pre-commit hook with black + ruff + mypy + pyright + pytest (CI-aligned)
  8 new ADRs (006-013) in .primer/adr/
  governance.md rewritten with 3-tier enforcement model
  Cross-platform .venv detection (POSIX + Windows)

Test count: 53 passing (was 39).

## Blockers / open questions

- MCPProbe._check_server() returns False (stubbed). Need enterprise MCP endpoint
  URLs from Claude Enterprise account config.
- knowledge/mastery/ is empty. Decision pending: copy from JARVIS or build fresh.
- Coverage gate at 50% in pyproject (raised from 40 in MVP Step 1, then to 100
  in Plan 2 -- but stub modules at 0% block 100%). Effective baseline tracked in
  .ratchet.json per module; full 100% achieved as stubs implement.

## Branch / remote state

Branch: main, in sync with origin/main at e073a56. Upstream tracking configured.
GitHub repo: https://github.com/pierregrothe/nexus-sn (public)
Tag: governance-baseline-2026-05-07 (pushed to GitHub release)
