# src/nexus/ui/components/panel.py
# KeyValuePanel: gradient-bordered panel of <coloured label> <neutral value> rows.
# Author: Pierre Grothe
# Date: 2026-05-11

"""KvRow / KeyValuePanel / two_col.

KvRow holds a label and value (string or Rich renderable). KeyValuePanel
arranges a list of KvRows inside a GradientPanel with brand-coloured
borders, padding labels to a common width. two_col composes two panels
side-by-side at equal height.
"""

import io

from pydantic import BaseModel, ConfigDict
from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.table import Table
from rich.text import Text

from nexus.ui.gradient_panel import GradientPanel
from nexus.ui.theme import SN_BLUE, SN_LIME

__all__ = ["KeyValuePanel", "KvRow", "two_col"]


class KvRow(BaseModel):
    """A single ``<gradient-label>: <value> [suffix]`` row.

    Attributes:
        label: The label text rendered with the per-character gradient.
        value: A plain string or any Rich renderable (e.g. a ``StatusBadge``).
        suffix: Optional renderable appended after the value with two-space
            separation, used for inline status badges.
    """

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    label: str
    value: RenderableType
    suffix: RenderableType | None = None


class KeyValuePanel(BaseModel):
    """Gradient-bordered panel of K/V rows.

    Attributes:
        title: Title shown on the top border.
        rows: The K/V rows in render order.
        min_height: Minimum body line count, used by ``two_col`` to equalise
            heights of side-by-side panels.
    """

    model_config = ConfigDict(
        frozen=True,
        strict=True,
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    title: str
    rows: list[KvRow]
    min_height: int = 0

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Render the panel with brand gradient borders and padded rows.

        Args:
            console: Destination console (unused).
            options: Render options (unused).

        Yields:
            A single ``GradientPanel`` containing the body Text.
        """
        del console, options
        body = self._body()
        yield GradientPanel(
            body,
            title=self.title,
            start=SN_BLUE,
            end=SN_LIME,
            min_height=self.min_height,
        )

    def _body(self) -> Text:
        """Build the multi-line body with labels padded to the longest.

        Returns:
            ``rich.text.Text`` with one line per row.
        """
        if not self.rows:
            return Text()
        pad = max(len(row.label) for row in self.rows) + 2
        out = Text()
        for i, row in enumerate(self.rows):
            label_str = f"{row.label}:"
            out.append(label_str, style="bold bright_white")
            out.append(" " * (pad - len(label_str)))
            if isinstance(row.value, str):
                out.append(row.value, style="value")
            else:
                out.append_text(_render_inline(row.value))
            if row.suffix is not None:
                out.append("  ")
                if isinstance(row.suffix, str):
                    out.append(row.suffix)
                else:
                    out.append_text(_render_inline(row.suffix))
            if i < len(self.rows) - 1:
                out.append("\n")
        return out


def two_col(left: KeyValuePanel, right: KeyValuePanel) -> RenderableType:
    """Compose two KeyValuePanels side-by-side at equal height.

    Args:
        left: Left-column panel.
        right: Right-column panel.

    Returns:
        A ``Table.grid`` rendering ``left`` and ``right`` in equal-ratio columns.
    """
    height = max(len(left.rows), len(right.rows))
    left_eq = left.model_copy(update={"min_height": height})
    right_eq = right.model_copy(update={"min_height": height})
    grid = Table.grid(expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(left_eq, right_eq)
    return grid


def _render_inline(renderable: RenderableType) -> Text:
    """Render a Rich renderable as inline ``Text`` via a temporary Console.

    Args:
        renderable: Anything ``Console.print`` accepts.

    Returns:
        ``rich.text.Text`` holding the captured plain output without trailing
        newline.
    """
    if isinstance(renderable, Text):
        return renderable
    capture_console = Console(
        file=io.StringIO(), force_terminal=False, color_system=None, width=200
    )
    with capture_console.capture() as cap:
        capture_console.print(renderable, end="")
    return Text(cap.get())
