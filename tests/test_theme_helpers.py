# tests/test_theme_helpers.py
# Tests for severity_color() and truncate_middle() helpers in theme.py.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Cover the HSL severity gradient and middle-truncation helper."""

import pytest

from nexus.ui.theme import severity_color, truncate_middle


def test_severitycolor_zero_returns_pure_green() -> None:
    assert severity_color(0) == "rgb(0,255,0)"


def test_severitycolor_hundred_returns_pure_red() -> None:
    assert severity_color(100) == "rgb(255,0,0)"


def test_severitycolor_fifty_returns_yellow() -> None:
    assert severity_color(50) == "rgb(255,255,0)"


def test_severitycolor_negative_clamps_to_zero() -> None:
    assert severity_color(-10) == severity_color(0)


def test_severitycolor_over_hundred_clamps_to_hundred() -> None:
    assert severity_color(150) == severity_color(100)


def test_severitycolor_returns_rich_compatible_format() -> None:
    color = severity_color(25)
    assert color.startswith("rgb(")
    assert color.endswith(")")


def test_truncatemiddle_returns_text_unchanged_when_short() -> None:
    assert truncate_middle("short", width=20) == "short"


def test_truncatemiddle_elides_long_text_in_middle() -> None:
    result = truncate_middle("abcdefghijklmnop", width=8)
    assert len(result) == 8
    assert "..." in result
    assert result.startswith("ab") or result.startswith("a")


def test_truncatemiddle_preserves_prefix_and_suffix() -> None:
    result = truncate_middle("sn_grc_advanced_dependencies_v3", width=12)
    assert len(result) == 12
    assert result.startswith("sn_")
    assert result.endswith("v3") or result.endswith("3")


def test_truncatemiddle_with_zero_width_raises() -> None:
    with pytest.raises(ValueError, match="positive"):
        truncate_middle("text", width=0)


def test_truncatemiddle_with_negative_width_raises() -> None:
    with pytest.raises(ValueError, match="positive"):
        truncate_middle("text", width=-3)


def test_truncatemiddle_when_marker_too_large_raises() -> None:
    with pytest.raises(ValueError, match="marker"):
        truncate_middle("text", width=3, marker="....")


def test_truncatemiddle_with_custom_marker() -> None:
    result = truncate_middle("abcdefghij", width=7, marker="*")
    assert "*" in result
    assert len(result) == 7


def test_truncatemiddle_zero_suffix_when_marker_consumes_room() -> None:
    result = truncate_middle("abcdef", width=5, marker="....")
    assert len(result) == 5
    assert result.endswith("....")
