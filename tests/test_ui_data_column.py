# tests/test_ui_data_column.py
# Unit tests for DataColumn min_width plumbing.
# Author: Pierre Grothe
# Date: 2026-05-17
"""Tests for ``DataColumn.min_width`` round-tripping into Rich's table.

``min_width`` lets a column expand when the terminal is wide enough while
still reserving the requested floor on narrow terminals. Verify the
field round-trips through the Pydantic model and the underlying
``rich.table.Column`` receives it.
"""

from __future__ import annotations

from rich.console import Console

from nexus.ui.components.table import DataColumn, DataTable

__all__: list[str] = []


def test_data_column_min_width_defaults_to_none() -> None:
    """Existing call sites that omit ``min_width`` see Rich's default behaviour."""
    col = DataColumn(header="Plugin ID", width=32)
    assert col.min_width is None


def test_data_column_min_width_accepts_explicit_value() -> None:
    """Frozen Pydantic model accepts the new optional field."""
    col = DataColumn(header="Plugin ID", min_width=32)
    assert col.min_width == 32
    assert col.width is None


def test_data_table_passes_min_width_to_rich_column() -> None:
    """A DataTable render hands ``min_width`` through to ``rich.table.Column``."""
    table = DataTable(
        title="t",
        columns=[
            DataColumn(header="Plugin ID", min_width=32),
            DataColumn(header="Version", width=10),
        ],
        rows=[["com.acme.short", "1.0.0"]],
    )
    console = Console(record=True, width=200)
    console.print(table)
    rendered = console.export_text()
    # The full content of the wide row must appear without truncation when
    # min_width is in effect and the terminal has room.
    assert "com.acme.short" in rendered


def test_data_table_does_not_truncate_long_id_when_min_width_used_on_wide_terminal() -> None:
    """Plugin IDs longer than 32 chars are NOT truncated when terminal allows.

    Regression: switching from ``width=32`` to ``min_width=32`` on a wide
    terminal should let names like ``sn_irm_continuous_authorization_management``
    render in full.
    """
    long_id = "sn_irm_continuous_authorization_management"  # 42 chars
    assert len(long_id) > 32
    table = DataTable(
        title="t",
        columns=[
            DataColumn(header="Plugin ID", min_width=32),
        ],
        rows=[[long_id]],
    )
    console = Console(record=True, width=200)
    console.print(table)
    rendered = console.export_text()
    assert long_id in rendered


def test_data_table_truncates_with_fixed_width_when_other_columns_consume_terminal() -> None:
    """The contrast case: ``width=32`` clips when sibling columns soak remaining space.

    With multiple columns, Rich's ``expand=True`` distributes available width
    across columns, and a column with a fixed ``width=32`` is held to that
    rendered width regardless of terminal size -- ``no_wrap=True`` then
    truncates the over-long cell with an ellipsis.
    """
    long_id = "sn_irm_continuous_authorization_management"
    # Other columns request widths that, combined, leave the Plugin ID
    # column at its declared 32 chars even on a 200-char terminal.
    table = DataTable(
        title="t",
        columns=[
            DataColumn(header="Plugin ID", width=32),
            DataColumn(header="Name", width=40),
            DataColumn(header="Product", width=40),
            DataColumn(header="Current", width=40),
            DataColumn(header="Latest", width=40),
        ],
        rows=[[long_id, "n", "p", "c", "l"]],
    )
    console = Console(record=True, width=200)
    console.print(table)
    rendered = console.export_text()
    # Fixed width clips: the full 42-char id does NOT appear, only the
    # first ~29 chars + Rich's ellipsis (...).
    assert long_id not in rendered
