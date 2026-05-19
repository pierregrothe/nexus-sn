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
from nexus.ui.capabilities import ColorDepth, RenderProfile, TerminalCapabilities
from nexus.ui.render_context import RenderContext
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


def test_status_reporter_shows_no_integrations_message_when_none_detected() -> None:
    """Empty detected set produces a placeholder, no server names leaked."""
    out = _render(_detection(tier=Tier.PRO, detected=frozenset(), reauth=frozenset()))
    assert "PRO" in out
    assert "No enterprise integrations detected." in out
    for label in (
        "Value Melody",
        "Sales Success Center",
        "BT1",
        "Data Analytics",
        "GTM",
        "Microsoft 365",
        "Marketing MCP",
    ):
        assert label not in out


def test_status_reporter_shows_only_detected_servers() -> None:
    """Only detected servers appear; undetected servers are not listed."""
    out = _render(
        _detection(
            tier=Tier.ENTERPRISE,
            detected=frozenset({MCPServer.VALUE_MELODY, MCPServer.SSC}),
            reauth=frozenset({MCPServer.SSC}),
        )
    )
    assert "READY" in out
    assert "NEEDS REAUTH" in out
    assert "Value Melody" in out
    assert "Sales Success Center" in out
    assert "BT1" not in out


def test_status_reporter_renders_runtime_panels() -> None:
    """Identity / System / Integrations / Diagnostics / Auto-update panels appear."""
    out = _render(_detection(tier=Tier.PRO, detected=frozenset(), reauth=frozenset()))
    for header in ("Identity", "System", "Integrations", "Diagnostics", "Auto-update"):
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


def test_status_reporter_identity_panel_shows_kv_labels() -> None:
    """Identity rows render their KvRow labels in the plain output."""
    out = _render(_detection(tier=Tier.PRO, detected=frozenset(), reauth=frozenset()))
    for label in ("User:", "Org:", "Tier:", "Version:"):
        assert label in out


def test_status_reporter_system_panel_shows_python_platform_install_labels() -> None:
    out = _render(_detection(tier=Tier.PRO, detected=frozenset(), reauth=frozenset()))
    for label in ("Python:", "Platform:", "Install:"):
        assert label in out


def test_status_reporter_servers_row_includes_reauth_badge_when_any_need_reauth() -> None:
    """When any detected server needs reauth, the Servers row shows the count badge."""
    out = _render(
        _detection(
            tier=Tier.ENTERPRISE,
            detected=frozenset({MCPServer.VALUE_MELODY, MCPServer.MARKETING}),
            reauth=frozenset({MCPServer.MARKETING}),
        )
    )
    assert "1/2 ready" in out
    assert "1 need reauth" in out


def test_status_reporter_single_server_reauth_footer_uses_warning_prefix() -> None:
    """The Notice.warn footer is rendered with the 'Warning:' prefix."""
    out = _render(
        _detection(
            tier=Tier.ENTERPRISE,
            detected=frozenset({MCPServer.MARKETING}),
            reauth=frozenset({MCPServer.MARKETING}),
        )
    )
    assert "Warning:" in out
    assert "nexus reauth --server marketing" in out


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


def _render_with_context(profile: RenderProfile, *, term_program: str = "WindowsTerminal") -> str:
    detection = _detection(tier=Tier.PRO, detected=frozenset(), reauth=frozenset())
    capabilities = CapabilitySet.from_detection(detection)
    caps = TerminalCapabilities(
        is_tty=True,
        is_ci=False,
        color_depth=ColorDepth.TRUECOLOR,
        cols=120,
        rows=40,
        legacy_windows=False,
        term_program=term_program,
        is_dumb_terminal=False,
        is_multiplexer=False,
        no_color_env=False,
        forced_plain=False,
        supports_hyperlinks=True,
    )
    console = Console(record=True, width=120, force_terminal=False, theme=NEXUS_THEME)
    render_ctx = RenderContext(console=console, caps=caps, profile=profile)
    StatusReporter(console=console).print(detection, capabilities, render_context=render_ctx)
    return console.export_text()


def test_status_reporter_terminal_panel_renders_profile_name() -> None:
    out = _render_with_context(RenderProfile.RICH)
    assert "Terminal" in out
    assert "RICH" in out


def test_status_reporter_terminal_panel_shows_framed_for_rich() -> None:
    out = _render_with_context(RenderProfile.RICH)
    assert "framed" in out


def test_status_reporter_terminal_panel_shows_inline_for_plain() -> None:
    out = _render_with_context(RenderProfile.PLAIN)
    assert "inline" in out


def test_status_reporter_terminal_panel_shows_color_and_size() -> None:
    out = _render_with_context(RenderProfile.RICH)
    assert "TRUECOLOR" in out
    assert "120x40" in out


def test_status_reporter_terminal_panel_falls_back_when_term_program_empty() -> None:
    out = _render_with_context(RenderProfile.RICH, term_program="")
    assert "default" in out


def test_status_reporter_without_render_context_omits_terminal_panel() -> None:
    detection = _detection(tier=Tier.PRO, detected=frozenset(), reauth=frozenset())
    capabilities = CapabilitySet.from_detection(detection)
    console = Console(record=True, width=120, force_terminal=False, theme=NEXUS_THEME)
    StatusReporter(console=console).print(detection, capabilities)
    assert "Terminal" not in console.export_text()
