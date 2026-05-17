# src/nexus/cli/formats.py
# Shared --format validation and JSON emission helpers.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Format-related helpers shared by every command that supports ``--format``.

Extracted from ``cli/__init__.py`` per ADR-023. Centralizing here means
the accepted format set is declared in one place and CI-script consumers
get identical, single-line JSON regardless of which command emits it.
"""

from __future__ import annotations

import typer
from pydantic import BaseModel, ConfigDict

from nexus.cli.console import console
from nexus.plugins.models import PluginInfo
from nexus.ui import Notice

__all__ = [
    "_OrphansReport",
    "_UpdatesReport",
    "_emit_json",
    "_validate_format",
]


_FORMATS = ("text", "json")


class _OrphansReport(BaseModel):
    """Inline wrapper for JSON output of nexus plugins orphans.

    Attributes:
        candidates: Plugins identified as orphan candidates.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    candidates: tuple[PluginInfo, ...]


class _UpdatesReport(BaseModel):
    """Inline wrapper for JSON output of nexus plugins updates.

    Attributes:
        updates: Plugins with newer versions available.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    updates: tuple[PluginInfo, ...]


def _validate_format(value: str) -> None:
    """Reject unknown ``--format`` values with a clear error.

    Args:
        value: User-provided format string.

    Raises:
        typer.Exit: With code 1 on unknown values, after printing
            a Notice.error to the console.
    """
    if value not in _FORMATS:
        console.print(Notice.error(f"Unknown --format: {value}"))
        raise typer.Exit(1)


def _emit_json(model: BaseModel) -> None:
    """Print model JSON serialization to stdout, one line.

    Uses ``model.model_dump_json()`` (not Rich's print_json) so the
    output is single-line and CI-script-friendly.

    Args:
        model: Any Pydantic model to serialize.
    """
    print(model.model_dump_json())
