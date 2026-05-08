# tests/test_ui_theme.py
# Tests for the NEXUS rich theme.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.ui.theme."""

from nexus.ui.theme import NEXUS_BLUE, NEXUS_CYAN, NEXUS_THEME


def test_theme_defines_required_named_styles() -> None:
    expected = {"primary", "accent", "info", "ok", "warning", "error", "muted"}
    assert expected.issubset(NEXUS_THEME.styles.keys())


def test_theme_primary_uses_nexus_blue_rgb() -> None:
    style = NEXUS_THEME.styles["primary"]
    assert str(NEXUS_BLUE[0]) in str(style)
    assert str(NEXUS_BLUE[1]) in str(style)
    assert str(NEXUS_BLUE[2]) in str(style)


def test_theme_accent_uses_nexus_cyan_rgb() -> None:
    style = NEXUS_THEME.styles["accent"]
    assert str(NEXUS_CYAN[0]) in str(style)
    assert str(NEXUS_CYAN[1]) in str(style)
    assert str(NEXUS_CYAN[2]) in str(style)
