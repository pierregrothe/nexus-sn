# src/nexus/ui/components/framed_viewer.py
# Sticky-frame TUI viewer built on Textual: pinned panels + virtual-scroll body.
# Author: Pierre Grothe
# Date: 2026-05-15

"""TUI table viewer using Textual's DataTable for fast virtual scrolling.

The viewer pins the CommandHelp panel + optional CommandGuide above a
DataTable whose column headers stay sticky while rows scroll. A summary
notice and key-bindings hint pin below. j/k/arrows/PageUp/PageDown drive
scroll natively in DataTable; ``q`` exits; ``?`` toggles the expandable
subcommand guide.

Tier 1 interactive features:
    ``/`` inline filter -- live substring filter across all cell text.
    ``Enter`` on a row -- opens a centered :class:`_DetailModal` with the
        caller-provided detail renderable for that row (if any).
    Column header click or ``s`` -- sorts that column, toggling direction.
    ``r`` -- invokes ``refresh_callback`` (if set) and reloads the rows.
    ``y`` -- copy the first cell of the current row (typically plugin_id)
        to the system clipboard via OSC 52.
    ``Y`` -- copy the whole row (tab-separated) to the system clipboard.
"""

from collections.abc import Callable
from io import StringIO
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict
from rich.console import Console, RenderableType
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Static

from nexus.ui.banner import gradient
from nexus.ui.components.table import DataColumn
from nexus.ui.theme import NEXUS_THEME, SN_BLUE, SN_LIME

__all__ = ["DetailsType", "FramedViewer", "RefreshCallback", "RowsType"]

RowsType = tuple[tuple[RenderableType, ...], ...]
DetailsType = tuple[RenderableType, ...]
RefreshCallback = Callable[[], tuple[RowsType, DetailsType]]


def _safe_width(console: Console) -> int:
    """Return the usable render width (1 column right margin)."""
    return max(1, (console.width or 120) - 1)


def _render_renderables_to_ansi(renderables: tuple[RenderableType, ...], console: Console) -> str:
    """Render a sequence of Rich renderables to a single ANSI string.

    The capture console carries the NEXUS theme so style names resolve to
    real colors; without it Rich raises :class:`rich.errors.MissingStyle`.
    """
    if not renderables:
        return ""
    buf = StringIO()
    capture_console = Console(
        file=buf,
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
        width=_safe_width(console),
        highlight=False,
        theme=NEXUS_THEME,
    )
    for renderable in renderables:
        capture_console.print(renderable)
    return buf.getvalue().rstrip("\n")


def _build_render_console() -> Console:
    """Build the shared wide truecolor Console used by cell-rendering helpers.

    Created once and reused across every `_cell_to_text` call so we avoid the
    cost of constructing a Rich Console per cell (each construction probes
    terminal capabilities).
    """
    return Console(
        file=StringIO(),
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
        width=10_000,
        highlight=False,
        theme=NEXUS_THEME,
    )


_CELL_RENDER_CONSOLE = _build_render_console()


def _cell_to_text(cell: RenderableType) -> Text:
    """Convert a cell to a single-line styled Text for DataTable."""
    if isinstance(cell, Text):
        text = cell.copy()
    elif isinstance(cell, str):
        text = Text(cell)
    else:
        buf = _CELL_RENDER_CONSOLE.file
        cast("StringIO", buf).seek(0)
        cast("StringIO", buf).truncate(0)
        _CELL_RENDER_CONSOLE.print(cell, end="")
        text = Text.from_ansi(cast("StringIO", buf).getvalue())
    if "\n" in text.plain:
        text = Text(text.plain.replace("\n", " "))
    return text


def _row_plain_text(row: tuple[RenderableType, ...]) -> str:
    """Return a single concatenated lowercase plain-text string for a row.

    Used by the filter to match against; pre-computed once per row at startup
    so the filter hot path is a single substring scan per row instead of N
    Rich renderings per keystroke.
    """
    parts: list[str] = []
    for cell in row:
        if isinstance(cell, str):
            parts.append(cell)
        elif isinstance(cell, Text):
            parts.append(cell.plain)
        else:
            parts.append(_cell_to_text(cell).plain)
    return " ".join(parts).casefold()


class FramedViewer(BaseModel):
    """Sticky-frame TUI table viewer with a scrollable row body.

    Attributes:
        header_renderables: Always-visible renderables above the table.
        expandable_renderables: Renderables shown only when ``?`` is pressed.
        title: Table title shown above the column-header row.
        columns: Column descriptors.
        rows: Tuple of cell tuples; the scrollable body.
        row_details: Optional tuple of detail renderables parallel to
            :attr:`rows`. When a row is highlighted and Enter is pressed,
            its detail (if any) opens in a centered modal popup. Empty
            tuple means Enter is a no-op.
        footer_renderables: Renderables shown below the table.
        refresh_callback: Optional zero-arg callable invoked when the user
            presses ``r``. Must return a fresh ``(rows, row_details)`` pair.
            ``None`` disables the refresh action.
    """

    model_config = ConfigDict(
        frozen=True, strict=True, extra="forbid", arbitrary_types_allowed=True
    )

    header_renderables: tuple[RenderableType, ...]
    expandable_renderables: tuple[RenderableType, ...]
    title: str
    columns: tuple[DataColumn, ...]
    rows: RowsType
    row_details: DetailsType = ()
    footer_renderables: tuple[RenderableType, ...]
    refresh_callback: RefreshCallback | None = None

    def run(self, console: Console) -> None:  # pragma: no cover -- requires real TTY.
        """Build a Textual ``App`` and run it until the user quits."""
        app = _FramedApp(viewer=self, console=console)
        app.run()


class _DetailModal(ModalScreen[None]):  # pragma: no cover -- TUI runtime.
    """Centered modal overlay that displays one row's detail renderable.

    Dismissed by ``Enter`` / ``Escape`` / ``q``. The underlying screen is
    automatically dimmed by Textual's ModalScreen behaviour, which gives
    the popup a "lifted" feel; the modal itself has a brand-blue rounded
    border and a subtle outline that reads as a drop shadow on most
    terminals.
    """

    DEFAULT_CSS: ClassVar[str] = f"""
    _DetailModal {{
        align: center middle;
        background: $background 70%;
    }}
    #nexus-detail-container {{
        width: 80%;
        max-width: 120;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: round rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]});
        outline: tall $boost;
        padding: 1 2;
    }}
    #nexus-detail-content {{
        height: auto;
        max-height: 100%;
    }}
    #nexus-detail-hint {{
        color: $text-muted;
        padding-top: 1;
    }}
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", "Close", show=False),
        Binding("enter", "dismiss", "Close", show=False),
        Binding("q", "dismiss", "Close", show=False),
    ]

    def __init__(self, detail: RenderableType) -> None:
        """Capture the detail renderable to show inside the modal."""
        super().__init__()
        self._detail = detail

    def compose(self) -> ComposeResult:
        """Build the modal layout."""
        with Vertical(id="nexus-detail-container"):
            yield Static(self._detail, id="nexus-detail-content")
            yield Static("Enter / Esc / q to close", id="nexus-detail-hint")

    async def action_dismiss(self, result: None = None) -> None:
        """Close the modal."""
        del result
        self.dismiss(None)


class _FramedApp(App[None]):  # pragma: no cover -- TUI runtime; needs real TTY.
    """Internal Textual application driving the framed viewer."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("escape", "blur_filter", "Quit / clear filter", show=False),
        Binding("question_mark", "toggle_expandable", "Toggle commands"),
        Binding("slash", "focus_filter", "Filter"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "sort_next_column", "Sort column"),
        Binding("y", "yank_id", "Yank id"),
        Binding("Y", "yank_row", "Yank row"),
    ]

    DEFAULT_CSS: ClassVar[str] = f"""
    Screen {{
        layout: vertical;
        background: $background;
    }}
    #nexus-header,
    #nexus-footer,
    #nexus-hint {{
        height: auto;
        padding: 0;
    }}
    #nexus-hint {{
        color: $text-muted;
    }}
    #nexus-expandable {{
        height: auto;
        display: none;
    }}
    #nexus-expandable.shown {{
        display: block;
    }}
    #nexus-filter {{
        height: 1;
        display: none;
        border: none;
        padding: 0 1;
    }}
    #nexus-filter.shown {{
        display: block;
    }}
    #nexus-table-title {{
        height: 1;
        padding: 0 1;
    }}
    #nexus-table-frame {{
        height: 1fr;
        border: round rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]});
        padding: 0;
    }}
    DataTable {{
        height: 1fr;
    }}
    DataTable > .datatable--header {{
        background: rgb({SN_BLUE[0]},{SN_BLUE[1]},{SN_BLUE[2]}) 15%;
    }}
    """

    def __init__(self, *, viewer: FramedViewer, console: Console) -> None:
        """Capture the viewer + Rich console for compose-time use.

        ``_live_rows`` and ``_live_details`` are the single source of truth
        for what the DataTable holds. ``_viewer`` is read-only -- its
        ``rows`` / ``row_details`` are the initial dataset only. Refresh,
        sort, and filter operate on the live state.
        """
        super().__init__()
        self._viewer = viewer
        self._console = console
        self._live_rows: RowsType = viewer.rows
        self._live_details: DetailsType = viewer.row_details
        self._row_search_text: list[str] = [_row_plain_text(row) for row in viewer.rows]
        self._row_index_map: list[int] = list(range(len(viewer.rows)))
        self._sort_state: dict[int, bool] = {}
        self._next_sort_col: int = 0
        self._last_query: str = ""

    def compose(self) -> ComposeResult:
        """Build the widget tree."""
        header_ansi = _render_renderables_to_ansi(self._viewer.header_renderables, self._console)
        if header_ansi:
            yield Static(Text.from_ansi(header_ansi), id="nexus-header")

        expandable_ansi = _render_renderables_to_ansi(
            self._viewer.expandable_renderables, self._console
        )
        if expandable_ansi:
            yield Static(Text.from_ansi(expandable_ansi), id="nexus-expandable")

        title_text = gradient(self._viewer.title, start=SN_BLUE, end=SN_LIME)
        title_text.stylize("bold")
        yield Static(title_text, id="nexus-table-title")

        yield Input(placeholder="Filter (substring across all cells)", id="nexus-filter")
        table: DataTable[str | Text] = DataTable(id="nexus-data")
        yield Container(table, id="nexus-table-frame")

        footer_ansi = _render_renderables_to_ansi(self._viewer.footer_renderables, self._console)
        if footer_ansi:
            yield Static(Text.from_ansi(footer_ansi), id="nexus-footer")

        bindings = [
            "j/k or arrows: scroll",
            "PgUp/PgDn: page",
            "Enter/click: detail",
            "/: filter",
            "s: sort",
            "y: copy id",
            "Y: copy row",
        ]
        if self._viewer.refresh_callback is not None:
            bindings.append("r: refresh")
        bindings.extend(("?: commands", "q: quit"))
        yield Static("   ".join(bindings), id="nexus-hint")

    def on_mount(self) -> None:
        """Populate the DataTable with columns and rows after the layout mounts."""
        table = cast("DataTable[str | Text]", self.query_one("#nexus-data", DataTable))
        table.cursor_type = "row"
        table.zebra_stripes = True
        for col in self._viewer.columns:
            table.add_column(col.header, width=col.width)
        self._repopulate_visible(self._live_rows, self._live_details)

    def _repopulate_visible(self, rows: RowsType, details: DetailsType) -> None:
        """Replace the DataTable's visible rows and rebuild the index map.

        ``rows`` and ``details`` are the currently visible (filtered/sorted)
        slice. The index map records each visible row's position in the
        live dataset so the detail modal can look up the right entry.
        """
        table = cast("DataTable[str | Text]", self.query_one("#nexus-data", DataTable))
        table.clear()
        self._row_index_map = []
        for source_index, row in enumerate(rows):
            cells = tuple(_cell_to_text(cell) for cell in row)
            table.add_row(*cells)
            self._row_index_map.append(source_index)
        self._live_rows = rows
        self._live_details = details

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_toggle_expandable(self) -> None:
        """Toggle the visibility of the expandable subcommand region."""
        for widget in self.query("#nexus-expandable"):
            if "shown" in widget.classes:
                widget.remove_class("shown")
            else:
                widget.add_class("shown")

    def action_focus_filter(self) -> None:
        """Show the filter input bar and focus it."""
        widget = self.query_one("#nexus-filter", Input)
        widget.add_class("shown")
        widget.focus()

    def action_blur_filter(self) -> None:
        """Hide the filter input and return focus to the table, or quit."""
        widget = self.query_one("#nexus-filter", Input)
        if widget.has_focus or "shown" in widget.classes:
            widget.value = ""
            widget.remove_class("shown")
            self.query_one("#nexus-data", DataTable).focus()
            return
        self.exit()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Apply the live filter as the user types.

        Filters against the pre-computed plain-text cache rather than
        re-rendering each cell's Rich content per keystroke. Skips the
        DataTable rebuild when the query is unchanged.
        """
        if event.input.id != "nexus-filter":
            return
        query = event.value.casefold()
        if query == self._last_query:
            return
        self._last_query = query
        if not query:
            filtered_rows = self._viewer.rows
            filtered_details = self._viewer.row_details
        else:
            filtered_rows_list: list[tuple[RenderableType, ...]] = []
            filtered_details_list: list[RenderableType] = []
            for index, search_text in enumerate(self._row_search_text):
                if query in search_text:
                    filtered_rows_list.append(self._viewer.rows[index])
                    if index < len(self._viewer.row_details):
                        filtered_details_list.append(self._viewer.row_details[index])
            filtered_rows = tuple(filtered_rows_list)
            filtered_details = tuple(filtered_details_list)
        self._repopulate_visible(filtered_rows, filtered_details)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Hide the filter bar on Enter but keep the filter applied."""
        if event.input.id != "nexus-filter":
            return
        widget = self.query_one("#nexus-filter", Input)
        widget.remove_class("shown")
        self.query_one("#nexus-data", DataTable).focus()

    def _show_row_detail(self, cursor_row: int) -> None:
        """Push the detail modal for the cursor row, if a detail exists."""
        if not self._live_details:
            return
        if cursor_row < 0 or cursor_row >= len(self._row_index_map):
            return
        source_index = self._row_index_map[cursor_row]
        if source_index >= len(self._live_details):
            return
        detail = self._live_details[source_index]
        self.push_screen(_DetailModal(detail))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Show the detail modal when a DataTable row is selected.

        DataTable emits :class:`DataTable.RowSelected` on ``Enter`` (in
        row-cursor mode) and on click. Listening here covers both paths
        without fighting the widget for the Enter key.
        """
        self._show_row_detail(event.cursor_row)

    def action_refresh(self) -> None:
        """Invoke the caller-provided ``refresh_callback`` and rebind rows.

        Updates the live dataset (which the filter and sort paths read from)
        without mutating the immutable :class:`FramedViewer` model.
        """
        callback = self._viewer.refresh_callback
        if callback is None:
            return
        new_rows, new_details = callback()
        self._row_search_text = [_row_plain_text(row) for row in new_rows]
        self._last_query = ""
        # Re-seat the viewer-shadowing buffers; the model itself stays frozen.
        # The filter reads from ``self._viewer.rows`` for the full set, so
        # callers that pass a refresh_callback get a fresh model copy.
        self._viewer = self._viewer.model_copy(
            update={"rows": new_rows, "row_details": new_details}
        )
        self._repopulate_visible(new_rows, new_details)

    def action_sort_next_column(self) -> None:
        """Sort the table by the next column in round-robin order."""
        column_count = len(self._viewer.columns)
        if column_count == 0:
            return
        index = self._next_sort_col % column_count
        reverse = self._sort_state.get(index, False)
        self._sort_state[index] = not reverse
        self._sort_by_column_index(index, reverse=reverse)
        self._next_sort_col = (index + 1) % column_count

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Sort by the clicked column header, toggling direction."""
        column_index = event.column_index
        reverse = self._sort_state.get(column_index, False)
        self._sort_state[column_index] = not reverse
        self._sort_by_column_index(column_index, reverse=reverse)

    def _sort_by_column_index(self, column_index: int, *, reverse: bool) -> None:
        """Sort the table rows by the given column index."""
        if column_index >= len(self._viewer.columns):
            return

        def _key(pair: tuple[int, tuple[RenderableType, ...]]) -> str:
            cell = pair[1][column_index] if column_index < len(pair[1]) else ""
            if isinstance(cell, str):
                return cell
            if isinstance(cell, Text):
                return cell.plain
            return _cell_to_text(cell).plain

        indexed = list(enumerate(self._live_rows))
        indexed.sort(key=_key, reverse=reverse)
        sorted_rows = tuple(row for _, row in indexed)
        sorted_details: tuple[RenderableType, ...] = ()
        if self._live_details:
            old_map = list(self._row_index_map)
            sorted_details = tuple(
                self._live_details[old_map[old_idx]]
                for old_idx, _ in indexed
                if old_map[old_idx] < len(self._live_details)
            )
        self._repopulate_visible(sorted_rows, sorted_details)

    async def action_quit(self) -> None:
        """Exit the app immediately.

        Defined explicitly to bypass any ``App.action_quit`` confirmation
        flow shipped by future Textual versions, and to guarantee the
        ``q`` binding always terminates the viewer. Async to match the
        :class:`App` base signature.
        """
        self.exit()

    def _cursor_live_row(self) -> tuple[RenderableType, ...] | None:
        """Return the cells of the row under the cursor, or ``None`` if absent."""
        table = cast("DataTable[str | Text]", self.query_one("#nexus-data", DataTable))
        cursor_row = table.cursor_row
        if cursor_row < 0 or cursor_row >= len(self._row_index_map):
            return None
        source_index = self._row_index_map[cursor_row]
        if source_index >= len(self._live_rows):
            return None
        return self._live_rows[source_index]

    def action_yank_id(self) -> None:
        """Copy the first cell of the current row (typically plugin_id) to clipboard.

        Uses :meth:`App.copy_to_clipboard` which writes via OSC 52, supported by
        Windows Terminal, iTerm2, Kitty, Alacritty, and most modern terminals.
        """
        row = self._cursor_live_row()
        if row is None or not row:
            return
        text = _cell_to_text(row[0]).plain
        if not text:
            return
        self.copy_to_clipboard(text)
        self.notify(f"Copied: {text}", timeout=2)

    def action_yank_row(self) -> None:
        """Copy every cell of the current row (tab-separated) to clipboard."""
        row = self._cursor_live_row()
        if row is None or not row:
            return
        text = "\t".join(_cell_to_text(cell).plain for cell in row)
        if not text:
            return
        self.copy_to_clipboard(text)
        preview = text if len(text) <= 60 else text[:57] + "..."
        self.notify(f"Copied row: {preview}", timeout=2)

    async def on_key(self, event: Key) -> None:
        """Intercept filter-related keys and the quit / toggle shortcuts.

        The DataTable widget consumes ordinary character keys when it is
        focused, so App-level priority bindings for ``q``, ``?``, ``s``,
        and ``r`` can be swallowed before they fire. We catch those keys
        here whenever the filter input is not focused. ``escape`` is
        handled explicitly to either clear the filter or exit.
        """
        focused = self.focused
        filter_focused = focused is not None and focused.id == "nexus-filter"
        if event.key == "q" and not filter_focused:
            event.prevent_default()
            event.stop()
            self.exit()
            return
        if event.key == "question_mark" and not filter_focused:
            event.prevent_default()
            event.stop()
            self.action_toggle_expandable()
            return
        if event.key == "s" and not filter_focused:
            event.prevent_default()
            event.stop()
            self.action_sort_next_column()
            return
        if event.key == "r" and not filter_focused:
            event.prevent_default()
            event.stop()
            self.action_refresh()
            return
        if event.key == "y" and not filter_focused:
            event.prevent_default()
            event.stop()
            self.action_yank_id()
            return
        if event.key == "Y" and not filter_focused:
            event.prevent_default()
            event.stop()
            self.action_yank_row()
            return
        if event.key == "escape" and filter_focused:
            event.prevent_default()
            event.stop()
            self.action_blur_filter()
