# ADR-018: Tier detection from Claude Code OAuth + org MCP config

**Status:** accepted
**Date:** 2026-05-08
**Enforcement:** none (architectural)

## Context

NEXUS already had a capabilities layer (FeatureFlag, MCPServer, FEATURE_MAP,
CapabilitySet, MCPProbe), but `_check_server` was a stub returning False, so
no features ever became available. Real detection was needed.

Three signals are available without live MCP probing:
  1. The Claude Code OAuth payload's `subscriptionType` (read from macOS
     Keychain or ~/.claude/.credentials.json).
  2. ~/.claude.json `claudeAiMcpEverConnected` -- the list of org-pushed
     MCP servers visible to this user.
  3. ~/.claude/mcp-needs-auth-cache.json -- per-server entries flagging
     re-authentication need.

Empirical investigation on 2026-05-08 (in this user's environment) confirmed
the OAuth payload directly carries `"subscriptionType": "enterprise"`. The
config and re-auth files contain the org MCP and re-auth state. No email
heuristic is needed.

## Decision

Add Tier (StrEnum: ANONYMOUS / PRO / ENTERPRISE) and TierDetector to the
existing capabilities layer. TierDetector reads the three sources via a
ClaudeCodeConfigReader Protocol and resolves a tier:

  - subscription_type == "enterprise" -> Tier.ENTERPRISE
  - subscription_type is None and no org MCP -> Tier.ANONYMOUS
  - else -> Tier.PRO
  - Override: if claudeAiMcpEverConnected is non-empty, the resolved tier
    is upgraded to Tier.ENTERPRISE regardless of the claim. Org MCP
    presence is the strongest signal.

CapabilitySet gains `tier` and `needs_reauth` fields plus a `from_detection`
factory. StatusReporter renders a Rich panel + per-server table for `nexus
status`. `nexus reauth` prints the exact `claude /mcp <name>` command for
each flagged server.

The detector is `@cached(ttl=None)` (in-memory per-instance, infinite within
the process). Cross-invocation disk caching was deferred -- the @cached
decorator's persist=True path captures the disk backend at decoration time,
which prevents tests from redirecting it to tmp_path. Each `nexus`
invocation re-runs detection in <100ms (1 keychain read + 2 small JSON
reads); not worth the complexity of fixing the decorator just for that
optimization.

No live MCP probing in this PR. The OAuth claim plus claudeAiMcpEverConnected
inspection is sufficient. `MCPProbe._check_server` stays a stub for the
future live-probe path.

## Consequences

  - `nexus status` works end-to-end; `nexus reauth` is a new command.
  - Cross-platform credential lookup: keyring on macOS routes to Keychain
    Access; Linux/Windows fall back to `~/.claude/.credentials.json`.
  - The static `CLAUDE_AI_NAME_TO_SERVER` table is SN-specific. If a new
    SN MCP server lands without updating the table, it is dropped at
    DEBUG-log level and does not appear in status output. NEXUS stays
    forward-compatible (no errors), but the new server is invisible
    until the table is updated.
  - Re-auth automation is print-only by default. Subprocess execution via
    `--execute` was scoped out; the print path is sufficient for v1.
  - Adds `MCPServer.MARKETING` to the existing enum.
  - `_CLAUDE_AI_NAME_TO_SERVER` (private) renamed to `CLAUDE_AI_NAME_TO_SERVER`
    (public) so tier.py can import it from feature_flags without violating
    pyright strict's reportPrivateUsage.

Spec: docs/superpowers/specs/2026-05-08-tier-detection-design.md
Plan: docs/superpowers/plans/2026-05-08-tier-detection.md
