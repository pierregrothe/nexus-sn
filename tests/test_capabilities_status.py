# tests/test_capabilities_status.py
# Tests for StatusReporter Rich panel rendering.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.capabilities.status_reporter."""

from rich.console import Console

from nexus.capabilities.claude_config import ClaudeCodeConfig
from nexus.capabilities.feature_flags import MCPServer
from nexus.capabilities.registry import CapabilitySet
from nexus.capabilities.status_reporter import (
    StatusReporter,
    _humanize_age,
    _humanize_bytes,
)
from nexus.capabilities.tier import Tier, TierDetection
from nexus.ui.theme import NEXUS_THEME


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
    console = Console(record=True, width=120, force_terminal=False, theme=NEXUS_THEME)
    StatusReporter(console=console).print(detection, capabilities)
    return console.export_text()


def test_status_reporter_anonymous_panel_says_anonymous() -> None:
    out = _render(_detection(tier=Tier.ANONYMOUS, detected=frozenset(), reauth=frozenset()))
    assert "ANONYMOUS" in out


def test_status_reporter_enterprise_panel_says_enterprise_and_lists_servers() -> None:
    out = _render(
        _detection(
            tier=Tier.ENTERPRISE,
            detected=frozenset({MCPServer.VALUE_MELODY, MCPServer.BT1}),
            reauth=frozenset(),
        )
    )
    assert "ENTERPRISE" in out
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
    assert "NEEDS REAUTH" in out
    assert "nexus reauth" in out


def test_status_reporter_lists_every_server_even_when_none_configured() -> None:
    """All 7 known servers always appear, with status indicating configuration."""
    out = _render(_detection(tier=Tier.PRO, detected=frozenset(), reauth=frozenset()))
    assert "PRO" in out
    for label in (
        "Value Melody",
        "Sales Success Center",
        "BT1",
        "Data Analytics",
        "GTM",
        "Microsoft 365",
        "Marketing MCP",
    ):
        assert label in out
    assert "not configured" in out


def test_status_reporter_marks_unconfigured_separately_from_ready_and_reauth() -> None:
    out = _render(
        _detection(
            tier=Tier.ENTERPRISE,
            detected=frozenset({MCPServer.VALUE_MELODY, MCPServer.SSC}),
            reauth=frozenset({MCPServer.SSC}),
        )
    )
    assert "READY" in out
    assert "NEEDS REAUTH" in out
    assert "not configured" in out


def test_status_reporter_renders_runtime_panels() -> None:
    """System / Account / Diagnostics / Auto-update panels appear."""
    out = _render(_detection(tier=Tier.PRO, detected=frozenset(), reauth=frozenset()))
    for header in ("System", "Account", "Diagnostics", "Auto-update", "MCP Servers"):
        assert header in out


def test_status_reporter_multi_server_reauth_footer_lists_each() -> None:
    out = _render(
        _detection(
            tier=Tier.ENTERPRISE,
            detected=frozenset({MCPServer.MARKETING, MCPServer.BT1}),
            reauth=frozenset({MCPServer.MARKETING, MCPServer.BT1}),
        )
    )
    assert "for:" in out
    assert "marketing" in out
    assert "bt1" in out


def test_humanize_bytes_covers_all_size_buckets() -> None:
    assert _humanize_bytes(0) == "0 B"
    assert _humanize_bytes(2048).endswith("KB")
    assert _humanize_bytes(5 * 1024 * 1024).endswith("MB")
    assert _humanize_bytes(3 * 1024 * 1024 * 1024).endswith("GB")


def test_humanize_age_covers_all_buckets() -> None:
    assert _humanize_age(None) == "never"
    assert _humanize_age(15) == "15 seconds ago"
    assert _humanize_age(120) == "2 minutes ago"
    assert _humanize_age(7200).endswith("hours ago")
    assert _humanize_age(2 * 86400).endswith("days ago")
