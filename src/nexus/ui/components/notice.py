# src/nexus/ui/components/notice.py
# Single-line user notice (Error: / Warning: / Info: prefix + neutral message).
# Author: Pierre Grothe
# Date: 2026-05-11

"""Notice: a one-line user-facing message.

The prefix word is colour-coded by severity; the message stays in the
terminal's default foreground colour.
"""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

__all__ = ["Notice"]

_PREFIX: dict[str, tuple[str, str]] = {
    "error": ("Error", "error"),
    "warn": ("Warning", "warn"),
    "info": ("Info", "label"),
}


class Notice(BaseModel):
    """A coloured-prefix neutral-message line.

    Attributes:
        severity: One of ``"error"``, ``"warn"``, ``"info"``.
        message: The neutral text rendered after the prefix.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    severity: Literal["error", "warn", "info"]
    message: str

    @classmethod
    def error(cls, message: str) -> Self:
        """Build an ``error`` notice (red bold prefix)."""
        return cls(severity="error", message=message)

    @classmethod
    def warn(cls, message: str) -> Self:
        """Build a ``warn`` notice (yellow bold prefix)."""
        return cls(severity="warn", message=message)

    @classmethod
    def info(cls, message: str) -> Self:
        """Build an ``info`` notice (blue label-style prefix)."""
        return cls(severity="info", message=message)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield ``<prefix>: <message>`` with prefix in the severity style.

        Args:
            console: Destination console (unused).
            options: Render options (unused).

        Yields:
            A single ``rich.text.Text``.
        """
        del console, options
        word, style = _PREFIX[self.severity]
        text = Text()
        text.append(f"{word}: ", style=style)
        text.append(self.message)
        yield text
