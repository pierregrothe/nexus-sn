# tests/ui/components/test_marker.py
# Tests for default_marker helper.
# Author: Pierre Grothe
# Date: 2026-05-11

import io

from rich.console import Console
from rich.text import Text

from nexus.ui.components.marker import default_marker
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def test_default_marker_returns_text() -> None:
    assert isinstance(default_marker(), Text)


def test_default_marker_text_is_asterisk_space() -> None:
    assert default_marker().plain == "* "


def test_default_marker_uses_ok_style() -> None:
    assert default_marker().style == "ok"


def test_default_marker_renders_with_ansi_in_terminal() -> None:
    console = Console(
        record=True,
        force_terminal=True,
        color_system="truecolor",
        theme=NEXUS_THEME,
        width=20,
    )
    console.print(default_marker(), end="")
    styled = console.export_text(styles=True)
    assert "*" in styled
    assert "\x1b[" in styled


def test_default_marker_renders_plain_when_not_terminal() -> None:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, theme=NEXUS_THEME, width=20)
    console.print(default_marker(), end="")
    out = buffer.getvalue()
    assert "*" in out
    assert "\x1b[" not in out
