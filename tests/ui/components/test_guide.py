# tests/ui/components/test_guide.py
# Tests for the CommandGuide component.
# Author: Pierre Grothe
# Date: 2026-05-11

"""Tests for CommandGuide."""

import io

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.guide import CommandGuide
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


def test_commandguide_construction_holds_app_name_and_items() -> None:
    guide = CommandGuide(
        app_name="nexus instance",
        items=[("register <profile>", "Add an instance")],
    )
    assert guide.app_name == "nexus instance"
    assert guide.items == [("register <profile>", "Add an instance")]


def test_commandguide_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CommandGuide.model_validate({"app_name": "x", "items": [], "extra": "y"})


def test_commandguide_is_frozen() -> None:
    guide = CommandGuide(app_name="x", items=[("a", "b")])
    with pytest.raises(ValidationError):
        setattr(guide, "app_name", "y")


def test_commandguide_renders_title_commands_descriptions_and_footer() -> None:
    console = _record_console()
    console.print(
        CommandGuide(
            app_name="nexus instance",
            items=[
                ("register <profile>", "Add an instance"),
                ("list", "Show all registered instances"),
            ],
        )
    )
    plain = console.export_text(styles=False)
    assert "nexus instance" in plain
    assert "register <profile>" in plain
    assert "Add an instance" in plain
    assert "list" in plain
    assert "Show all registered instances" in plain
    assert "Run nexus instance <command> --help for details." in plain


def test_commandguide_renders_plain_when_not_terminal() -> None:
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=False,
        theme=NEXUS_THEME,
        width=80,
    )
    console.print(CommandGuide(app_name="x", items=[("a", "b")]))
    out = buffer.getvalue()
    assert "x a" in out
    assert "b" in out
    assert "\x1b[" not in out
