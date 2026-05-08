# ADR-001: API-direct architecture (no Claude Code dependency)

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** none

## Context

JARVIS required Claude Code + MCP protocol + Node.js, limiting deployment to
developers who had Claude Desktop or Claude Code installed. This prevented
use in CI pipelines, headless environments, or any machine without a Claude
desktop client.

## Decision

NEXUS calls the Anthropic API directly using the Python SDK. No Claude Code,
no MCP protocol, no Node.js. Ships as a pip package that runs on Windows,
macOS, and Linux identically.

## Consequences

NEXUS can be installed anywhere Python runs. Enterprise MCP servers (Value
Melody, SSC, BT1, etc.) are accessed via the Claude Enterprise API key's
server-sent events channel, not via a local MCP host process. The capability
probing layer must handle absent enterprise MCP gracefully -- features
gated on unavailable servers are disabled transparently rather than failing.

## Update 2026-05-08: Partially superseded by ADR-015

The "no Claude Code dependency" claim is partially superseded. NEXUS still
ships as a pip package and is invoked as `nexus <command>` (not as a Claude
Code plugin). However, the underlying LLM access goes through claude-agent-sdk,
which bundles Claude Code CLI as a subprocess dependency.

User-facing distribution and invocation are unchanged. Implementation is
no longer Claude-Code-independent.
