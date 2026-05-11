# tests/ui/components/test_hint.py
# Tests for Hint component.
# Author: Pierre Grothe
# Date: 2026-05-11

import io

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.hint import Hint
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def _record_console() -> Console:
    return Console(
        file=io.StringIO(),
        record=True,
        force_terminal=True,
        color_system="truecolor",
        theme=NEXUS_THEME,
        width=80,
    )


def test_hint_construction_defaults_suffix_to_none() -> None:
    hint = Hint(label="Next", command="nexus capture pull --scope x_foo")
    assert hint.suffix is None


def test_hint_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Hint(label="Next", command="x", extra="y")  # type: ignore[call-arg]


def test_hint_is_frozen() -> None:
    hint = Hint(label="Next", command="x")
    with pytest.raises(ValidationError):
        hint.command = "y"  # type: ignore[misc]


def test_hint_renders_with_two_space_leading_indent() -> None:
    console = _record_console()
    console.print(Hint(label="Next", command="nexus capture pull"))
    plain = console.export_text(styles=False)
    assert plain.startswith("  Next:")


def test_hint_renders_label_command_and_suffix() -> None:
    console = _record_console()
    console.print(Hint(label="Next", command="nexus capture pull", suffix="(repeatable)"))
    plain = console.export_text(styles=False)
    assert "Next:" in plain
    assert "nexus capture pull" in plain
    assert "(repeatable)" in plain


def test_hint_omits_suffix_when_none() -> None:
    console = _record_console()
    console.print(Hint(label="Next", command="nexus capture pull"))
    plain = console.export_text(styles=False)
    assert "(" not in plain


def test_hint_emits_ansi_for_label_in_terminal() -> None:
    console = _record_console()
    console.print(Hint(label="Next", command="nexus capture pull"))
    styled = console.export_text(styles=True)
    assert "\x1b[" in styled


def test_hint_renders_plain_when_not_terminal() -> None:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, theme=NEXUS_THEME, width=80)
    console.print(Hint(label="Next", command="nexus capture pull"))
    out = buffer.getvalue()
    assert "Next:" in out
    assert "nexus capture pull" in out
    assert "\x1b[" not in out
