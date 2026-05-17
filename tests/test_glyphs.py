# tests/test_glyphs.py
# Tests for the ASCII glyph palette + glyph() factory.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Cover GLYPHS keys and glyph() Text generation."""

import pytest

from nexus.ui.glyphs import GLYPHS, STYLES, glyph


def test_glyphs_palette_has_expected_keys() -> None:
    assert set(GLYPHS) == {"ok", "err", "pending", "arrow", "active"}


def test_glyphs_palette_is_ascii_only() -> None:
    for value in GLYPHS.values():
        assert value.isascii()


def test_styles_has_an_entry_for_every_glyph() -> None:
    assert set(STYLES) == set(GLYPHS)


def test_glyph_returns_text_with_default_style() -> None:
    text = glyph("ok")
    assert text.plain == "[ok]"
    assert str(text.style) == STYLES["ok"]


def test_glyph_returns_text_with_override_style() -> None:
    text = glyph("ok", style="dim")
    assert text.plain == "[ok]"
    assert str(text.style) == "dim"


def test_glyph_with_unknown_name_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        glyph("unknown")


def test_glyph_err_maps_to_error_style() -> None:
    assert str(glyph("err").style) == "error"


def test_glyph_pending_maps_to_dim_style() -> None:
    assert str(glyph("pending").style) == "dim"


def test_glyph_arrow_maps_to_label_style() -> None:
    assert str(glyph("arrow").style) == "label"


def test_glyph_active_maps_to_ok_style() -> None:
    assert str(glyph("active").style) == "ok"
