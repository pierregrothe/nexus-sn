# tests/ui/components/test_table.py
# Tests for DataColumn / DataTable.
# Author: Pierre Grothe
# Date: 2026-05-11

import io

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.badge import StatusBadge
from nexus.ui.components.table import DataColumn, DataTable
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def _record_console(width: int = 80) -> Console:
    return Console(
        file=io.StringIO(),
        record=True,
        force_terminal=True,
        color_system="truecolor",
        theme=NEXUS_THEME,
        width=width,
    )


def test_datacolumn_construction_defaults() -> None:
    col = DataColumn(header="Profile")
    assert col.header == "Profile"
    assert col.width is None
    assert col.justify == "left"
    assert col.no_wrap is True


def test_datacolumn_rejects_invalid_justify() -> None:
    with pytest.raises(ValidationError):
        DataColumn(header="x", justify="middle")  # type: ignore[arg-type]


def test_datacolumn_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DataColumn(header="x", extra="y")  # type: ignore[call-arg]


def test_datacolumn_is_frozen() -> None:
    col = DataColumn(header="x")
    with pytest.raises(ValidationError):
        col.header = "y"  # type: ignore[misc]


def test_datatable_construction_holds_columns_and_rows() -> None:
    tbl = DataTable(
        title="Instances",
        columns=[DataColumn(header="Profile"), DataColumn(header="URL")],
        rows=[["dev", "https://dev.service-now.com"]],
    )
    assert tbl.title == "Instances"
    assert len(tbl.columns) == 2
    assert tbl.rows == [["dev", "https://dev.service-now.com"]]


def test_datatable_is_frozen() -> None:
    tbl = DataTable(title="x", columns=[DataColumn(header="A")], rows=[["1"]])
    with pytest.raises(ValidationError):
        tbl.title = "y"  # type: ignore[misc]


def test_datatable_renders_title_headers_and_data() -> None:
    console = _record_console()
    console.print(
        DataTable(
            title="Instances",
            columns=[DataColumn(header="Profile"), DataColumn(header="Token")],
            rows=[
                ["dev", StatusBadge.ok("7h 30m")],
                ["prod", StatusBadge.error("EXPIRED")],
            ],
        )
    )
    plain = console.export_text(styles=False)
    assert "Instances" in plain
    assert "Profile" in plain
    assert "Token" in plain
    assert "dev" in plain
    assert "prod" in plain
    assert "7h 30m" in plain
    assert "EXPIRED" in plain


def test_datatable_renders_plain_cells_without_styling() -> None:
    console = _record_console()
    console.print(
        DataTable(
            title="x",
            columns=[DataColumn(header="A")],
            rows=[["plain-data"]],
        )
    )
    plain = console.export_text(styles=False)
    assert "plain-data" in plain


def test_datatable_renders_plain_when_not_terminal() -> None:
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=False,
        theme=NEXUS_THEME,
        width=80,
    )
    console.print(
        DataTable(
            title="x",
            columns=[DataColumn(header="A")],
            rows=[["b"]],
        )
    )
    out = buffer.getvalue()
    assert "A" in out
    assert "b" in out
    assert "\x1b[" not in out
