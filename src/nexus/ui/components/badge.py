# src/nexus/ui/components/badge.py
# Semantic state indicator (READY / NEEDS REAUTH / EXPIRED).
# Author: Pierre Grothe
# Date: 2026-05-11

"""StatusBadge: a single coloured word marking a semantic state.

ok    -> SN_LIME bold (READY, healthy)
warn  -> yellow bold  (NEEDS REAUTH, expiring)
error -> red bold     (EXPIRED, FAILED)
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

__all__ = ["StatusBadge"]


class StatusBadge(BaseModel):
    """A single semantic-coloured state word.

    Attributes:
        text: The word to render (e.g. ``"READY"``).
        variant: One of ``"ok"``, ``"warn"``, ``"error"`` mapped to the
            theme styles of the same name.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    text: str
    variant: Literal["ok", "warn", "error"]

    @classmethod
    def ok(cls, text: str) -> Self:
        """Build an ``ok`` badge (lime bold).

        Args:
            text: The word to render.

        Returns:
            A frozen ``StatusBadge`` with ``variant="ok"``.
        """
        return cls(text=text, variant="ok")

    @classmethod
    def warn(cls, text: str) -> Self:
        """Build a ``warn`` badge (yellow bold).

        Args:
            text: The word to render.

        Returns:
            A frozen ``StatusBadge`` with ``variant="warn"``.
        """
        return cls(text=text, variant="warn")

    @classmethod
    def error(cls, text: str) -> Self:
        """Build an ``error`` badge (red bold).

        Args:
            text: The word to render.

        Returns:
            A frozen ``StatusBadge`` with ``variant="error"``.
        """
        return cls(text=text, variant="error")

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield a styled Text whose style resolves to the theme variant.

        Args:
            console: Destination console (unused -- Text resolves the style
                against the console's theme at render time).
            options: Render options (unused).

        Yields:
            A single ``rich.text.Text`` carrying the badge text.
        """
        del console, options
        yield Text(self.text, style=self.variant)
