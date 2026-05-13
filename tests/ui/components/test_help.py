# tests/ui/components/test_help.py
# Tests for the CommandHelp component.
# Author: Pierre Grothe
# Date: 2026-05-12

"""Tests for CommandHelp / CommandHelpEntry."""

import io

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.help import CommandHelp, CommandHelpEntry
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


def test_commandhelpentry_holds_command_purpose_and_example() -> None:
    entry = CommandHelpEntry(command="list", purpose="P", example="nexus plugins list")
    assert entry.command == "list"
    assert entry.purpose == "P"
    assert entry.example == "nexus plugins list"


def test_commandhelpentry_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CommandHelpEntry.model_validate(
            {"command": "x", "purpose": "y", "example": "z", "extra": "no"}
        )


def test_commandhelpentry_is_frozen() -> None:
    entry = CommandHelpEntry(command="x", purpose="y", example="z")
    with pytest.raises(ValidationError):
        setattr(entry, "command", "y")


def test_commandhelp_renders_title_purpose_and_example() -> None:
    console = _record_console()
    console.print(
        CommandHelp(
            title="nexus plugins",
            entry=CommandHelpEntry(
                command="plugins",
                purpose="Inspect the plugin inventory.",
                example="nexus plugins list --product ITSM",
            ),
        )
    )
    plain = console.export_text(styles=False)
    assert "nexus plugins" in plain
    assert "Purpose:" in plain
    assert "Inspect the plugin inventory." in plain
    assert "Example:" in plain
    assert "nexus plugins list --product ITSM" in plain


def test_commandhelp_wraps_long_purpose_with_hanging_indent() -> None:
    """A long Purpose value should fold to subsequent lines, not run past the border."""
    long = (
        "This is a deliberately long purpose string that absolutely will not fit "
        "on one line of an 80-column terminal so we can confirm wrapping behavior."
    )
    console = _record_console()
    console.print(
        CommandHelp(
            title="nexus plugins",
            entry=CommandHelpEntry(command="x", purpose=long, example="nexus x"),
        )
    )
    plain = console.export_text(styles=False)
    # The full text must appear in the rendered output even though it wrapped.
    assert "deliberately long purpose string" in plain
    assert "wrapping behavior" in plain


def test_commandhelp_is_frozen() -> None:
    help_panel = CommandHelp(
        title="x",
        entry=CommandHelpEntry(command="a", purpose="b", example="c"),
    )
    with pytest.raises(ValidationError):
        setattr(help_panel, "title", "y")
