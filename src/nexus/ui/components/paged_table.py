# src/nexus/ui/components/paged_table.py
# Adaptive table rendering: pager / inline / ASCII / plain by profile.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Render a tabular view chosen by :class:`RenderProfile`.

Profiles dispatch to four strategies:

- RICH:   gradient-bordered DataTable, paged when output overflows.
- BASIC:  same DataTable but without gradient flourish, paged on overflow.
- LEGACY: ASCII box-drawing table, always inline (no VT pager).
- PLAIN:  tab-separated rows, one per line, no styling, no pager.
"""

from io import StringIO

from pydantic import BaseModel, ConfigDict
from rich.box import ASCII
from rich.console import Console, RenderableType
from rich.table import Table

from nexus.ui.capabilities import RenderProfile
from nexus.ui.components.pager import PagerProtocol
from nexus.ui.components.table import DataColumn, DataTable
from nexus.ui.render_context import RenderContext

__all__ = ["PagedTable"]


def _cell_to_plain(cell: RenderableType) -> str:
    """Render any cell to a single-line plain string with no ANSI escapes."""
    if isinstance(cell, str):
        return cell
    buf = StringIO()
    plain_console = Console(
        file=buf, color_system=None, force_terminal=False, no_color=True, width=10_000
    )
    plain_console.print(cell, end="")
    return buf.getvalue().rstrip("\n")


class PagedTable(BaseModel):
    """Tabular view that adapts to the active :class:`RenderProfile`.

    Attributes:
        title: Table title shown on the top border in styled profiles.
        columns: Column descriptors used by all profiles.
        rows: Row cells. Each cell may be a plain string or any Rich
            renderable. PLAIN/LEGACY paths flatten renderables to plain
            text via :func:`_cell_to_plain`.
    """

    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", arbitrary_types_allowed=True
    )

    title: str
    columns: tuple[DataColumn, ...]
    rows: tuple[tuple[RenderableType, ...], ...]

    def render(self, ctx: RenderContext, pager: PagerProtocol | None = None) -> None:
        """Print the table using the strategy mandated by ``ctx.profile``.

        Args:
            ctx: The active render context.
            pager: Pager backend used by RICH/BASIC when the table would
                overflow the terminal height. Ignored by LEGACY/PLAIN.
                Pass ``None`` to force inline rendering even on overflow.
        """
        match ctx.profile:
            case RenderProfile.RICH | RenderProfile.BASIC:
                self._render_styled(ctx.console, ctx, pager)
            case RenderProfile.LEGACY:
                self._render_legacy(ctx.console)
            case RenderProfile.PLAIN:
                self._render_plain(ctx.console)
            case _:  # pragma: no cover -- defensive default; RenderProfile is closed.
                self._render_plain(ctx.console)

    def _render_styled(
        self,
        console: Console,
        ctx: RenderContext,
        pager: PagerProtocol | None,
    ) -> None:
        """Render with DataTable + optional pypager on overflow."""
        data_table = DataTable(
            title=self.title,
            columns=list(self.columns),
            rows=[list(row) for row in self.rows],
        )
        overflow = pager is not None and len(self.rows) > max(1, ctx.caps.rows - 4)
        if overflow and pager is not None:
            with console.capture() as capture:
                console.print(data_table)
            pager.page(capture.get())
            return
        console.print(data_table)

    def _render_legacy(self, console: Console) -> None:
        """Render an ASCII box table without ANSI escapes."""
        table = Table(
            title=self.title,
            box=ASCII,
            show_header=True,
            pad_edge=False,
            expand=False,
        )
        for col in self.columns:
            table.add_column(
                header=col.header,
                width=col.width,
                justify=col.justify,
                no_wrap=col.no_wrap,
            )
        for row in self.rows:
            table.add_row(*(_cell_to_plain(cell) for cell in row))
        console.print(table)

    def _render_plain(self, console: Console) -> None:
        """Render tab-separated rows: header line + N data lines, no styling."""
        header_line = "\t".join(col.header for col in self.columns)
        print(header_line, file=console.file)
        for row in self.rows:
            print("\t".join(_cell_to_plain(cell) for cell in row), file=console.file)
