# src/nexus/ui/components/guide.py
# CommandGuide: subcommand listing rendered as a gradient-bordered panel.
# Author: Pierre Grothe
# Date: 2026-05-11

"""CommandGuide: the per-subapp command list (replacement for cli._print_command_guide).

Two-column layout: command in the brand gradient, description in dim,
wrapped in a GradientPanel titled with the app name. A dim footer line
points at ``--help`` for details.
"""

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, Group, RenderResult
from rich.table import Table
from rich.text import Text

from nexus.ui.gradient_panel import GradientPanel, gradient_text
from nexus.ui.theme import SN_BLUE, SN_LIME

__all__ = ["CommandGuide"]


class CommandGuide(BaseModel):
    """Subcommand listing wrapped in a gradient-bordered panel.

    Attributes:
        app_name: The fully-qualified Typer app path (e.g. ``"nexus instance"``).
        items: ``(subcommand, description)`` pairs in render order.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    app_name: str
    items: list[tuple[str, str]]

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield the GradientPanel-wrapped guide and its dim footer.

        Args:
            console: Destination console (unused).
            options: Render options (unused).

        Yields:
            One ``GradientPanel`` then one footer ``Text``.
        """
        del console, options
        table = Table(
            box=None,
            show_header=False,
            pad_edge=False,
            show_edge=False,
            padding=(0, 2),
            expand=True,
        )
        table.add_column("cmd", no_wrap=True, ratio=2, overflow="fold")
        table.add_column("desc", style="dim", ratio=3, overflow="fold")
        for cmd, desc in self.items:
            cmd_text = gradient_text(
                f"{self.app_name} {cmd}",
                start=SN_BLUE,
                end=SN_LIME,
            )
            cmd_text.stylize("bold")
            table.add_row(cmd_text, desc)
        panel = GradientPanel(
            table,
            title=self.app_name,
            start=SN_BLUE,
            end=SN_LIME,
        )
        footer = Text(
            f"  Run {self.app_name} <command> --help for details.",
            style="dim",
        )
        yield Group(panel, footer)
