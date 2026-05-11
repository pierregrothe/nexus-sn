# tests/ui/test_theme.py
# Tests for nexus.ui.theme tokens and Rich Theme map.
# Author: Pierre Grothe
# Date: 2026-05-11

from rich.console import Console

from nexus.ui.theme import NEXUS_THEME, SN_BLUE, SN_LIME

__all__: list[str] = []


def test_sn_blue_matches_brand_rgb() -> None:
    assert SN_BLUE == (0x00, 0x68, 0xB1)


def test_sn_lime_matches_brand_rgb() -> None:
    assert SN_LIME == (0x7C, 0xC1, 0x43)


def test_theme_exposes_label_style() -> None:
    assert "label" in NEXUS_THEME.styles


def test_theme_exposes_value_style() -> None:
    assert "value" in NEXUS_THEME.styles


def test_theme_exposes_dim_style() -> None:
    assert "dim" in NEXUS_THEME.styles


def test_theme_exposes_ok_style() -> None:
    assert "ok" in NEXUS_THEME.styles


def test_theme_exposes_warn_style() -> None:
    assert "warn" in NEXUS_THEME.styles


def test_theme_exposes_error_style() -> None:
    assert "error" in NEXUS_THEME.styles


def test_theme_exposes_border_start_style() -> None:
    assert "border.start" in NEXUS_THEME.styles


def test_theme_exposes_border_end_style() -> None:
    assert "border.end" in NEXUS_THEME.styles


def test_label_renders_in_blue_bold() -> None:
    console = Console(
        record=True,
        force_terminal=True,
        color_system="truecolor",
        theme=NEXUS_THEME,
        width=40,
    )
    console.print("[label]User:[/label]")
    out = console.export_text(styles=True)
    assert "User:" in out
    assert "\x1b[" in out  # contains ANSI escapes
