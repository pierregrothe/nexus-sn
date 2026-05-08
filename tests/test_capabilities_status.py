# tests/test_capabilities_status.py
# Tests for StatusReporter Rich panel rendering.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.capabilities.status_reporter."""

from rich.console import Console

from nexus.capabilities.claude_config import ClaudeCodeConfig
from nexus.capabilities.feature_flags import MCPServer
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.status_reporter import StatusReporter
from nexus.capabilities.tier import Tier, TierDetection


def _detection(
    *, tier: Tier, detected: frozenset[MCPServer], reauth: frozenset[MCPServer]
) -> TierDetection:
    return TierDetection(
        tier=tier,
        config=ClaudeCodeConfig(subscription_type=None, org_mcp_servers=(), needs_reauth=()),
        detected_servers=detected,
        needs_reauth_servers=reauth,
    )


def _render(detection: TierDetection) -> str:
    capabilities = CapabilitySet.from_detection(detection)
    console = Console(record=True, width=120, force_terminal=False)
    StatusReporter(console=console).print(detection, capabilities)
    return console.export_text()


def test_status_reporter_anonymous_panel_says_anonymous() -> None:
    out = _render(_detection(tier=Tier.ANONYMOUS, detected=frozenset(), reauth=frozenset()))
    assert "Anonymous" in out


def test_status_reporter_enterprise_panel_says_enterprise_and_lists_servers() -> None:
    out = _render(
        _detection(
            tier=Tier.ENTERPRISE,
            detected=frozenset({MCPServer.VALUE_MELODY, MCPServer.BT1}),
            reauth=frozenset(),
        )
    )
    assert "Enterprise" in out
    assert "Value Melody" in out
    assert "BT1" in out


def test_status_reporter_shows_needs_reauth_footer() -> None:
    out = _render(
        _detection(
            tier=Tier.ENTERPRISE,
            detected=frozenset({MCPServer.MARKETING}),
            reauth=frozenset({MCPServer.MARKETING}),
        )
    )
    assert "needs re-auth" in out.lower() or "needs reauth" in out.lower()
    assert "nexus reauth" in out


def test_status_reporter_pro_tier_does_not_mention_servers_when_none_detected() -> None:
    out = _render(_detection(tier=Tier.PRO, detected=frozenset(), reauth=frozenset()))
    assert "Pro" in out
    assert "Value Melody" not in out
