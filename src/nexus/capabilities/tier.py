# src/nexus/capabilities/tier.py
# Tier enum + TierDetector. Detects user tier from Claude Code state.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tier detection (ADR-018).

Anonymous = no Claude OAuth (API-key-only or unauthenticated).
Pro       = authenticated Claude account, no Enterprise MCP servers.
Enterprise = Claude Enterprise + ServiceNow MCP servers provisioned.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum

from nexus.cache import cached
from nexus.capabilities.claude_config import ClaudeCodeConfig, ClaudeCodeConfigReader
from nexus.capabilities.feature_flags import CLAUDE_AI_NAME_TO_SERVER, MCPServer

log = logging.getLogger(__name__)

__all__ = ["Tier", "TierDetection", "TierDetector"]


class Tier(StrEnum):
    """User capability tier derived from authentication and org MCP access."""

    ANONYMOUS = "anonymous"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass(slots=True, frozen=True)
class TierDetection:
    """Resolved tier detection snapshot.

    Attributes:
        tier: The resolved Tier.
        config: The raw ClaudeCodeConfig used to derive the tier (kept for UI).
        detected_servers: MCPServer enum values successfully mapped from
            org_mcp_servers via CLAUDE_AI_NAME_TO_SERVER.
        needs_reauth_servers: Subset of detected_servers currently flagged
            for re-authentication in mcp-needs-auth-cache.
    """

    tier: Tier
    config: ClaudeCodeConfig
    detected_servers: frozenset[MCPServer]
    needs_reauth_servers: frozenset[MCPServer]


class TierDetector:
    """Detect a user's NEXUS Tier from Claude Code config.

    Args:
        reader: ClaudeCodeConfigReader Protocol implementation.
    """

    def __init__(self, reader: ClaudeCodeConfigReader) -> None:
        """Initialize with a config reader."""
        self._reader = reader

    @cached(ttl=None)
    def detect(self) -> TierDetection:
        """Read Claude Code config and resolve to a TierDetection.

        Cached in-memory per-instance for the lifetime of the process.
        Each `nexus` invocation re-detects on first call (~10-50ms total).
        Tests call clear_cache(TierDetector.detect) to force a re-read.

        Returns:
            TierDetection with tier, raw config, and mapped server sets.
        """
        config = self._reader.read()
        detected = _map_servers(config.org_mcp_servers)
        needs_reauth = _map_servers(config.needs_reauth)
        tier = _resolve_tier(config.subscription_type, detected)
        log.info(
            "tier=%s; %d org MCP servers detected; %d need re-auth",
            tier,
            len(detected),
            len(needs_reauth),
        )
        return TierDetection(
            tier=tier,
            config=config,
            detected_servers=detected,
            needs_reauth_servers=needs_reauth,
        )


_KNOWN_SUBSCRIPTIONS = ("enterprise", "pro", "max")


def _resolve_tier(subscription_type: str | None, detected: frozenset[MCPServer]) -> Tier:
    """Map subscription claim + org MCP presence to a Tier.

    Org MCP presence is the strongest signal. If claudeAiMcpEverConnected is
    non-empty, the user is Enterprise regardless of the OAuth claim.

    Args:
        subscription_type: OAuth subscriptionType string, or None.
        detected: MCPServer values mapped from org_mcp_servers.

    Returns:
        The resolved Tier.
    """
    if subscription_type == "enterprise":
        initial = Tier.ENTERPRISE
    elif subscription_type is None and not detected:
        initial = Tier.ANONYMOUS
    else:
        if subscription_type not in (None, *_KNOWN_SUBSCRIPTIONS):
            log.debug("unknown subscription_type=%r; treating as Pro", subscription_type)
        initial = Tier.PRO

    if detected and initial is not Tier.ENTERPRISE:
        log.debug("org MCP servers present; upgrading tier to Enterprise")
        return Tier.ENTERPRISE
    return initial


def _map_servers(claude_ai_names: tuple[str, ...]) -> frozenset[MCPServer]:
    """Map claude.ai server-name strings to MCPServer enum values.

    Unrecognized names are dropped with a DEBUG log.

    Args:
        claude_ai_names: Strings from claudeAiMcpEverConnected or needs-reauth.

    Returns:
        frozenset of recognized MCPServer enum members.
    """
    mapped: set[MCPServer] = set()
    for name in claude_ai_names:
        server = CLAUDE_AI_NAME_TO_SERVER.get(name)
        if server is None:
            log.debug("unrecognized claude.ai MCP server name: %r", name)
            continue
        mapped.add(server)
    return frozenset(mapped)
