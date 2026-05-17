# src/nexus/ui/components/help.py
# CommandHelp: single Purpose/Example panel for one command node.
# Author: Pierre Grothe
# Date: 2026-05-12

"""CommandHelp / CommandHelpEntry.

Renders one gradient-bordered panel describing a single command's
purpose and a runnable example. Sub-app callbacks pair it with a
``CommandGuide`` listing the immediate subcommands.
"""

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderResult
from rich.table import Table
from rich.text import Text

from nexus.ui.gradient_panel import GradientPanel
from nexus.ui.theme import SN_BLUE, SN_LIME

__all__ = ["CommandHelp", "CommandHelpEntry"]


class CommandHelpEntry(BaseModel):
    """One command's purpose + runnable example.

    Attributes:
        command: Command text (e.g. ``"plugins"`` or ``"info <plugin_id>"``).
            Used both as Box-1 panel title (joined with the app path) and
            as the left column in the Box-2 subcommand listing.
        purpose: One- or two-sentence explanation.
        example: A runnable shell line (e.g.
            ``"nexus plugins list --product ITSM"``).
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    command: str
    purpose: str
    example: str


class CommandHelp(BaseModel):
    """Single gradient-bordered Purpose/Example panel for one command node.

    Attributes:
        title: Panel title (typically the fully-qualified command path,
            e.g. ``"nexus plugins"``).
        entry: The CommandHelpEntry to render.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    title: str
    entry: CommandHelpEntry

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield the gradient-bordered panel with hanging-indent rows.

        Args:
            console: Destination console (unused).
            options: Render options (unused).

        Yields:
            A single ``GradientPanel`` containing the Purpose/Example body.
        """
        del console, options
        body = Table.grid(padding=(0, 0))
        body.add_column(width=10, no_wrap=True)
        body.add_column(overflow="fold")
        body.add_row(
            Text("Purpose:  ", style="bold bright_white"),
            Text(self.entry.purpose, style="value"),
        )
        body.add_row(
            Text("Example:  ", style="bold bright_white"),
            Text(self.entry.example, style="value"),
        )
        yield GradientPanel(
            body,
            title=self.title,
            start=SN_BLUE,
            end=SN_LIME,
        )
