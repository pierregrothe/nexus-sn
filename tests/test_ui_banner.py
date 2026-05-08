# tests/test_ui_banner.py
# Tests for the gradient banner module.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.ui.banner."""

import io

from rich.console import Console

from nexus.ui.banner import banner_text, gradient, print_banner
from nexus.ui.theme import NEXUS_BLUE, NEXUS_CYAN


def test_gradient_returns_empty_text_for_empty_input() -> None:
    text = gradient("", start=NEXUS_BLUE, end=NEXUS_CYAN)
    assert str(text) == ""


def test_gradient_handles_single_character() -> None:
    text = gradient("A", start=NEXUS_BLUE, end=NEXUS_CYAN)
    assert str(text) == "A"
    # Single-char path bakes the start RGB into the Text's own style.
    assert str(NEXUS_BLUE[0]) in str(text.style)


def test_gradient_first_segment_uses_start_color() -> None:
    text = gradient("ABCDE", start=(255, 0, 0), end=(0, 0, 255))
    spans = list(text.render(_recording_console()))
    # First non-empty segment carries start RGB (255,0,0).
    first_styled = next(s for s in spans if s.text == "A")
    assert "255,0,0" in str(first_styled.style)


def test_gradient_last_segment_uses_end_color() -> None:
    text = gradient("ABCDE", start=(255, 0, 0), end=(0, 0, 255))
    spans = list(text.render(_recording_console()))
    last_styled = next(s for s in spans if s.text == "E")
    assert "0,0,255" in str(last_styled.style)


def test_gradient_interpolates_middle_character() -> None:
    text = gradient("ABC", start=(0, 0, 0), end=(100, 100, 100))
    spans = list(text.render(_recording_console()))
    middle = next(s for s in spans if s.text == "B")
    # Halfway between (0,0,0) and (100,100,100) -> 50
    assert "50,50,50" in str(middle.style)


def test_banner_text_contains_all_lines_and_tagline() -> None:
    text = banner_text()
    rendered = str(text)
    # The art uses block characters; just assert non-empty multi-line output.
    lines = rendered.splitlines()
    assert len(lines) >= 6
    assert "ServiceNow" in rendered


def test_print_banner_writes_when_terminal() -> None:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=True, width=120)
    print_banner(console)
    output = buf.getvalue()
    assert output  # non-empty
    assert "ServiceNow" in output


def test_print_banner_skips_when_not_terminal() -> None:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    print_banner(console)
    assert buf.getvalue() == ""


def _recording_console() -> Console:
    return Console(file=io.StringIO(), force_terminal=True, width=120, color_system="truecolor")
