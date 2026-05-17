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

from nexus.ui.gradient_panel import GradientPanel
from nexus.ui.theme import SN_BLUE, SN_LIME

__all__ = ["CommandGuide"]


class CommandGuide(BaseModel):
    """Subcommand listing wrapped in a gradient-bordered panel.

    Attributes:
        app_name: The fully-qualified Typer app path (e.g. ``"nexus instance"``).
            Used as the command prefix in each row.
        items: ``(subcommand, description)`` pairs in render order.
        title: Optional override for the panel title. Defaults to ``app_name``.
            Pass a different string (e.g. ``"available commands"``) to keep
            two adjacent panels visually distinct.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    app_name: str
    items: list[tuple[str, str]]
    title: str | None = None

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
        table.add_column("desc", style="value", ratio=3, overflow="fold")
        for cmd, desc in self.items:
            cmd_text = Text(f"{self.app_name} {cmd}", style="bold bright_white")
            table.add_row(cmd_text, desc)
        panel_title = self.title if self.title is not None else self.app_name
        panel = GradientPanel(
            table,
            title=panel_title,
            start=SN_BLUE,
            end=SN_LIME,
        )
        footer = Text(
            f"  Run {self.app_name} <command> --help for details.",
            style="dim",
        )
        yield Group(panel, footer)
