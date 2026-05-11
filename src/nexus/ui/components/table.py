# src/nexus/ui/components/table.py
# DataTable: gradient-bordered tabular display with coloured headers.
# Author: Pierre Grothe
# Date: 2026-05-11

"""DataColumn / DataTable.

DataTable wraps a Rich Table inside a GradientPanel. Headers carry the
brand gradient via gradient_text(); data cells render in the terminal's
default foreground style. Cells may be plain strings or Rich renderables
(StatusBadge, default_marker(), etc.).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.table import Table
from rich.text import Text

from nexus.ui.gradient_panel import GradientPanel, gradient_text
from nexus.ui.theme import SN_BLUE, SN_LIME

__all__ = ["DataColumn", "DataTable"]


def _to_text(cell: RenderableType, console: Console) -> RenderableType:
    """Convert a renderable cell into a measurable form for Rich's table layout.

    Rich's column auto-sizing relies on ``__rich_measure__``. Custom renderables
    without an explicit measure report ``min=0 max=available_width``, which
    collapses neighbouring columns. Rendering the cell to styled ``Text`` via
    the destination console makes its width measurable while preserving styles.

    Args:
        cell: A plain string, ``Text``, or any other Rich renderable.
        console: Destination console whose theme resolves named styles.

    Returns:
        ``cell`` unchanged for ``str`` / ``Text`` inputs; otherwise a ``Text``
        rebuilt from the renderable's segments.
    """
    if isinstance(cell, str | Text):
        return cell
    out = Text()
    for segment in console.render(cell):
        if segment.text == "\n":
            continue
        out.append(segment.text, style=segment.style)
    return out


class DataColumn(BaseModel):
    """Column descriptor for ``DataTable``.

    Attributes:
        header: Column header text rendered with the brand gradient.
        width: Optional fixed width in characters; ``None`` lets Rich auto-size.
        justify: Cell alignment.
        no_wrap: When ``True``, cells truncate rather than wrap.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    header: str
    width: int | None = None
    justify: Literal["left", "right", "center"] = "left"
    no_wrap: bool = True


class DataTable(BaseModel):
    """Tabular display with gradient borders and coloured headers.

    Attributes:
        title: Title shown on the top border.
        columns: Column descriptors in render order.
        rows: Row cells; each cell may be a plain string or a Rich renderable.
    """

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    title: str
    columns: list[DataColumn]
    rows: list[list[RenderableType]]

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Yield the GradientPanel-wrapped Rich Table.

        Args:
            console: Destination console; used to pre-render renderable cells
                so they measure correctly during Rich's column auto-sizing.
            options: Render options (unused).

        Yields:
            A single ``GradientPanel`` containing a ``rich.table.Table``.
        """
        del options
        table = Table(
            box=None,
            show_header=True,
            pad_edge=False,
            show_edge=False,
            expand=True,
        )
        for col in self.columns:
            header = gradient_text(col.header, start=SN_BLUE, end=SN_LIME)
            table.add_column(
                header=header,
                width=col.width,
                justify=col.justify,
                no_wrap=col.no_wrap,
            )
        for row in self.rows:
            table.add_row(*(_to_text(cell, console) for cell in row))
        yield GradientPanel(
            table,
            title=self.title,
            start=SN_BLUE,
            end=SN_LIME,
        )
