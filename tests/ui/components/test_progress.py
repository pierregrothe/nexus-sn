# tests/ui/components/test_progress.py
# Tests for the nexus_progress factory.
# Author: Pierre Grothe
# Date: 2026-05-11

"""Tests for nexus_progress factory."""

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from nexus.ui.components.progress import nexus_progress
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def test_nexus_progress_returns_progress_instance() -> None:
    console = Console(theme=NEXUS_THEME)
    progress = nexus_progress(console)
    assert isinstance(progress, Progress)


def test_nexus_progress_includes_expected_columns() -> None:
    console = Console(theme=NEXUS_THEME)
    progress = nexus_progress(console)
    types = [type(c) for c in progress.columns]
    assert SpinnerColumn in types
    assert TextColumn in types
    assert BarColumn in types
    assert MofNCompleteColumn in types
    assert TimeElapsedColumn in types


def test_nexus_progress_uses_provided_console() -> None:
    console = Console(theme=NEXUS_THEME)
    progress = nexus_progress(console)
    assert progress.console is console


def test_nexus_progress_is_transient() -> None:
    console = Console(theme=NEXUS_THEME)
    progress = nexus_progress(console)
    assert progress.live.transient is True
