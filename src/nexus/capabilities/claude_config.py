# src/nexus/capabilities/claude_config.py
# Reads Claude Code's local config to detect org-pushed MCP servers + tier.
# Author: Pierre Grothe
# Date: 2026-05-08
"""ClaudeCodeConfig: snapshot of Claude Code state relevant to NEXUS tier detection.

Reads three sources:
  1. OAuth payload (macOS Keychain -> ~/.claude/.credentials.json fallback)
     for the subscription_type claim.
  2. ~/.claude.json claudeAiMcpEverConnected list for org-pushed MCP servers.
  3. ~/.claude/mcp-needs-auth-cache.json for servers requiring re-authentication.
"""

from dataclasses import dataclass
from typing import Protocol

__all__ = ["ClaudeCodeConfig", "ClaudeCodeConfigReader"]


@dataclass(slots=True, frozen=True)
class ClaudeCodeConfig:
    """Snapshot of Claude Code's local config relevant to capability detection.

    Attributes:
        subscription_type: The OAuth payload's subscriptionType field
            ("enterprise", "pro", "max", etc.). None when no Claude Code
            credentials are present.
        org_mcp_servers: Strings from claudeAiMcpEverConnected in ~/.claude.json,
            e.g. "claude.ai ValueMelody". Empty tuple when not authenticated.
        needs_reauth: Server-name strings from ~/.claude/mcp-needs-auth-cache.json
            that currently need user re-authentication.
    """

    subscription_type: str | None
    org_mcp_servers: tuple[str, ...]
    needs_reauth: tuple[str, ...]


class ClaudeCodeConfigReader(Protocol):
    """Reader interface for ClaudeCodeConfig."""

    def read(self) -> ClaudeCodeConfig:
        """Return the current Claude Code config snapshot.

        Implementations must never raise; missing or malformed sources
        should yield empty/None fields.
        """
        ...
