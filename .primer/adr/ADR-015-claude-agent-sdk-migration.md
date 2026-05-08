# ADR-015: Migrate from anthropic SDK to claude-agent-sdk

**Status:** accepted
**Date:** 2026-05-08
**Enforcement:** none (architectural)

## Context

The 2026-05-07 decision (Pluggable AuthProvider) introduced two concrete
auth implementations: AnthropicAPIKeyProvider (X-Api-Key auth) and
ClaudeCodeOAuthProvider (Bearer auth via the user's Claude Code stored token).
The OAuth path was meant to bypass the API-key-acquisition friction for
ServiceNow employees who could not easily obtain an enterprise API key.

Empirical testing on 2026-05-08 showed the OAuth path is policy-gated by
Anthropic. With a valid OAuth token:
  - GET /v1/models returns 200
  - POST /v1/messages returns 429 immediately, on every call, on every
    retry, even with no recent traffic from the same token

This is not a transient rate limit. The error body lacks Retry-After headers
and details. The behavior matches Anthropic's stated policy that third-party
products may not use claude.ai login or rate limits.

A 10-line smoke test against `claude-agent-sdk` (Anthropic-published Python
SDK that wraps the bundled Claude Code CLI as a subprocess) succeeded against
the same /v1/messages endpoint with the same OAuth credentials, returning a
real assistant message with prompt caching active and access to Claude Opus
4.7 with 1M context.

## Decision

Replace the standard `anthropic` SDK with `claude-agent-sdk` as the LLM
access layer. The user-facing distribution model (pip package, `nexus`
CLI command) stays identical. Internally, LLM calls go through
`claude_agent_sdk.query()` which spawns the bundled Claude Code CLI as a
subprocess and authenticates using the user's stored credentials.

A new `AgentClient` class wraps `claude_agent_sdk.query()` with a simple
async interface: `async def complete(prompt, *, system, model, max_turns) -> str`.
The pluggable AuthProvider abstraction is deleted -- claude-agent-sdk handles
the auth resolution chain (env var > file > Keychain) internally.

## Consequences

NEXUS users who have Claude Code installed and authenticated (the target
audience: ServiceNow colleagues) get LLM access transparently with no API
key. This works for actual /v1/messages calls, not just metadata.

Tradeoffs accepted:
  - Bundled Claude Code CLI adds ~50MB to package install
  - Each `query()` invocation spawns a subprocess and runs SessionStart
    hooks (~10-30s startup cost on cold call)
  - The standard `anthropic` SDK is no longer a dependency
  - The Pluggable AuthProvider decision (2026-05-07) becomes superseded
  - ADR-001 (API-direct, no Claude Code dependency) becomes partially
    superseded -- still pip distribution, but Claude Code CLI is now a
    subprocess dependency

Headless / CI environments without Claude Code authenticated continue to
work via ANTHROPIC_API_KEY environment variable, which claude-agent-sdk
resolves first in its auth chain.
