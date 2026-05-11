# src/nexus/ui/components/hint.py
# "Next: <command>" style instructional line with baked-in two-space indent.
# Author: Pierre Grothe
# Date: 2026-05-11

"""Hint: one-line prompt pointing the user at the next command to run.

Format: ``  <label>: <command> <suffix?>`` -- label in the theme ``label`` style
(gradient blue->lime), command in bold default foreground, suffix in dim.
Two-space leading indent is part of the component, not the caller.
"""

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

__all__ = ["Hint"]


class Hint(BaseModel):
    """A coloured-label / bold-command instructional line.

    Attributes:
        label: Short prefix word (e.g. ``"Next"``, ``"Try"``).
        command: The literal command to run, rendered bold.
        suffix: Optional dim parenthetical shown after the command.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    label: str
    command: str
    suffix: str | None = None

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield ``  <label>: <command> <suffix>`` styled per the theme.

        Args:
            console: Destination console (unused).
            options: Render options (unused).

        Yields:
            A single ``rich.text.Text``.
        """
        del console, options
        text = Text("  ")
        text.append(f"{self.label}: ", style="label")
        text.append(self.command, style="bold")
        if self.suffix is not None:
            text.append(f" {self.suffix}", style="dim")
        yield text
