# tests/test_capabilities_tier.py
# Tests for nexus.capabilities.tier.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for the Tier enum and TierDetector."""

from nexus.capabilities.claude_config import ClaudeCodeConfig
from nexus.capabilities.feature_flags import MCPServer
from nexus.capabilities.tier import Tier, TierDetection, TierDetector
from tests.fakes.fake_claude_config import FakeClaudeCodeConfig


def _detect(config: ClaudeCodeConfig) -> TierDetection:
    """Build a fresh TierDetector with the given config and return its detection.

    @cached(ttl=None) is per-instance, so each new TierDetector starts with
    an empty cache. No fixture-level cleanup needed.
    """
    detector = TierDetector(reader=FakeClaudeCodeConfig(config=config))
    return detector.detect()


def test_tier_detector_returns_anonymous_when_no_credentials_and_no_org_mcp() -> None:
    detection = _detect(
        ClaudeCodeConfig(subscription_type=None, org_mcp_servers=(), needs_reauth=())
    )
    assert detection.tier is Tier.ANONYMOUS
    assert detection.detected_servers == frozenset()


def test_tier_detector_returns_pro_for_authenticated_no_org_mcp() -> None:
    detection = _detect(
        ClaudeCodeConfig(subscription_type="pro", org_mcp_servers=(), needs_reauth=())
    )
    assert detection.tier is Tier.PRO


def test_tier_detector_returns_enterprise_for_enterprise_claim() -> None:
    detection = _detect(
        ClaudeCodeConfig(subscription_type="enterprise", org_mcp_servers=(), needs_reauth=())
    )
    assert detection.tier is Tier.ENTERPRISE


def test_tier_detector_overrides_pro_to_enterprise_when_org_mcp_present() -> None:
    """Org MCP presence is the strongest signal; it wins over the OAuth claim."""
    detection = _detect(
        ClaudeCodeConfig(
            subscription_type="pro",
            org_mcp_servers=("claude.ai BT1_MCP",),
            needs_reauth=(),
        )
    )
    assert detection.tier is Tier.ENTERPRISE


def test_tier_detector_overrides_anonymous_to_enterprise_when_org_mcp_present() -> None:
    detection = _detect(
        ClaudeCodeConfig(
            subscription_type=None,
            org_mcp_servers=("claude.ai ValueMelody",),
            needs_reauth=(),
        )
    )
    assert detection.tier is Tier.ENTERPRISE


def test_tier_detector_maps_recognized_org_servers() -> None:
    detection = _detect(
        ClaudeCodeConfig(
            subscription_type="enterprise",
            org_mcp_servers=(
                "claude.ai ValueMelody",
                "claude.ai BT1_MCP",
                "claude.ai Microsoft 365",
            ),
            needs_reauth=(),
        )
    )
    assert detection.detected_servers == frozenset(
        {MCPServer.VALUE_MELODY, MCPServer.BT1, MCPServer.M365}
    )


def test_tier_detector_drops_unrecognized_org_server_names() -> None:
    detection = _detect(
        ClaudeCodeConfig(
            subscription_type="enterprise",
            org_mcp_servers=("claude.ai ValueMelody", "claude.ai SomethingNew"),
            needs_reauth=(),
        )
    )
    assert detection.detected_servers == frozenset({MCPServer.VALUE_MELODY})


def test_tier_detector_maps_needs_reauth_servers() -> None:
    detection = _detect(
        ClaudeCodeConfig(
            subscription_type="enterprise",
            org_mcp_servers=("claude.ai Marketing MCP",),
            needs_reauth=("claude.ai Marketing MCP",),
        )
    )
    assert detection.needs_reauth_servers == frozenset({MCPServer.MARKETING})


def test_tier_detector_unknown_subscription_falls_back_to_pro() -> None:
    detection = _detect(
        ClaudeCodeConfig(subscription_type="team", org_mcp_servers=(), needs_reauth=())
    )
    assert detection.tier is Tier.PRO


def test_tier_detection_carries_raw_config() -> None:
    cfg = ClaudeCodeConfig(
        subscription_type="enterprise", org_mcp_servers=("claude.ai BT1_MCP",), needs_reauth=()
    )
    detection = _detect(cfg)
    assert detection.config == cfg
