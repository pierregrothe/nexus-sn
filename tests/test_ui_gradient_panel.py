# tests/test_ui_gradient_panel.py
# Tests for GradientPanel renderable and gradient_text helper.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.ui.gradient_panel."""

import io
import re

from rich.console import Console
from rich.text import Text

from nexus.ui.gradient_panel import GradientPanel, gradient_text
from nexus.ui.theme import SN_BLUE, SN_LIME

_RED = (255, 0, 0)
_BLUE = (0, 0, 255)
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _console(width: int = 80) -> Console:
    return Console(file=io.StringIO(), force_terminal=True, width=width, color_system="truecolor")


def _plain(text: str) -> str:
    return _ANSI.sub("", text)


# ---------------------------------------------------------------------------
# gradient_text
# ---------------------------------------------------------------------------


def test_gradient_text_empty_string_returns_empty_text() -> None:
    result = gradient_text("", start=_RED, end=_BLUE)
    assert result.plain == ""


def test_gradient_text_single_char_uses_start_color() -> None:
    result = gradient_text("X", start=(100, 150, 200), end=(0, 0, 0))
    spans = list(result.render(_console()))
    assert any("100,150,200" in str(s.style) for s in spans if s.text == "X")


def test_gradient_text_last_char_uses_end_color() -> None:
    result = gradient_text("AB", start=_RED, end=_BLUE)
    spans = list(result.render(_console()))
    assert any("0,0,255" in str(s.style) for s in spans if s.text == "B")


# ---------------------------------------------------------------------------
# GradientPanel border rendering
# ---------------------------------------------------------------------------


def test_gradient_panel_renders_title_in_top_border() -> None:
    console = _console(60)
    panel = GradientPanel(Text("body"), title="Test", start=SN_BLUE, end=SN_LIME)
    with console.capture() as cap:
        console.print(panel)
    assert "Test" in _plain(cap.get())


def test_gradient_panel_renders_without_title() -> None:
    console = _console(60)
    panel = GradientPanel(Text("body"), title="", start=SN_BLUE, end=SN_LIME)
    with console.capture() as cap:
        console.print(panel)
    assert "body" in cap.get()


def test_gradient_panel_min_height_pads_shorter_content() -> None:
    console = _console(60)
    panel = GradientPanel(Text("one line"), title="T", start=SN_BLUE, end=SN_LIME, min_height=4)
    with console.capture() as cap:
        console.print(panel)
    # 4 content lines + 2 border lines = 6 lines minimum
    assert cap.get().count("\n") >= 6


def test_gradient_panel_rich_measure_reports_expandable_max() -> None:
    console = _console(80)
    panel = GradientPanel(Text("x"), title="T", start=SN_BLUE, end=SN_LIME)
    opts = console.options
    measure = panel.__rich_measure__(console, opts)
    assert measure.maximum == opts.max_width
    assert measure.minimum > 0
