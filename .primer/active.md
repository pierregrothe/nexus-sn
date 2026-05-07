# NEXUS -- Active Work

Last updated: 2026-05-07
Session: Pluggable AuthProvider implemented end-to-end (Plan 3, PR #1).

## Current focus

Pluggable AuthProvider feature complete on branch `feat/pluggable-auth`, PR #1
opened: https://github.com/pierregrothe/nexus-sn/pull/1

After merge, MVP Step 1 unblocks: smoke test against real Anthropic API can run
using Claude Code's stored OAuth token (no API key needed).

Next focus shifts back to MVP Step 2: GitHubSync.

  src/nexus/templates/sync.py -- implement GitHubSync.fetch_manifest() + download_changed()
  Test with tmp_path and a fake manifest fixture.

Build order from here (rest of 2026.05 milestone):
  Step 3: templates/registry.py -- TemplateRegistry.list() + get()
  Step 4: assessment/scanner.py -- InstanceScanner using ServiceNowClient
  Step 5: assessment/rules.py + reporter.py -- RuleEngine + AssessmentReporter
  Step 6: nexus setup command -- credential wizard, config write, initial sync
  Step 7: nexus status command -- probe capabilities, verify SN connectivity

## What was completed this session (Plan 3 + simplify)

Plan 3 -- Pluggable AuthProvider (8 commits on feat/pluggable-auth):
  src/nexus/auth/providers.py -- AuthProvider Protocol + get_default_providers()
                                  + AnthropicAPIKeyProvider alias
  src/nexus/auth/oauth.py -- ClaudeCodeOAuthProvider (env -> ~/.claude/.credentials.json
                              -> macOS Keychain via keyring lib)
  src/nexus/auth/claude.py -- ClaudeAuth implements AuthProvider Protocol
                               with cached get_api_key()
  src/nexus/api/client.py -- AnthropicClient takes auth_providers (was api_key str)
  tests/fakes/fake_auth_provider.py -- FakeAuthProvider test double
  tests/test_auth_providers.py -- 13 tests for OAuth provider + chain
  scripts/smoke_anthropic.py -- updated to use get_default_providers()

Simplify pass on top:
  - Subprocess "security find-generic-password" replaced with keyring.get_password()
  - is_configured() removed, body inlined into is_available()
  - Dead _TIER_DEFAULTS / _discover_model aliases dropped
  - Per-instance caching for token/api_key resolution
  - EAFP file read (drop redundant exists() stat + TOCTOU window)

Test count: 71 passing (was 53). Coverage up across auth modules.

## Blockers / open questions

- MCPProbe._check_server() still stubbed (returns False). With OAuth working,
  enterprise MCP probing is now possible -- but real endpoint URLs still needed.
- knowledge/mastery/ empty. Decision pending: copy from JARVIS or build fresh.
- Smoke test scripts/smoke_anthropic.py needs manual run after PR merge to
  validate end-to-end Anthropic API call against your enterprise account.

## Branch / remote state

Branch: feat/pluggable-auth, 8 commits ahead of main.
PR #1: https://github.com/pierregrothe/nexus-sn/pull/1 -- ready for merge.
After merge: switch back to main and start MVP Step 2 (GitHubSync) on a new branch.
