# tests/test_framed_viewer.py
# Unit tests for FramedViewer's Pydantic surface and renderable helper.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Cover the FramedViewer model + ANSI capture helper.

The full TUI runtime (Textual Application) requires a real TTY and is not
exercised here -- only the public model construction and the static ANSI
rendering used inside Textual's Static widgets.
"""

from io import StringIO

import pytest
from rich.console import Console
from rich.text import Text

from nexus.ui.components.framed_viewer import (
    FramedViewer,
    _cell_to_text,
    _render_renderables_to_ansi,
    _safe_width,
)
from nexus.ui.components.notice import Notice
from nexus.ui.components.table import DataColumn


def _plain_console() -> Console:
    return Console(file=StringIO(), force_terminal=True, color_system="truecolor", width=120)


def test_safewidth_subtracts_one_for_right_margin() -> None:
    console = Console(file=StringIO(), width=120)
    assert _safe_width(console) == 119


def test_safewidth_floor_is_one() -> None:
    console = Console(file=StringIO(), width=1)
    assert _safe_width(console) == 1


def test_renderrenderablestoansi_returns_empty_for_empty_tuple() -> None:
    assert _render_renderables_to_ansi((), _plain_console()) == ""


def test_renderrenderablestoansi_renders_notice() -> None:
    out = _render_renderables_to_ansi((Notice.info("hello world"),), _plain_console())
    assert "hello world" in out


def test_celltotext_from_plain_string_returns_text() -> None:
    text = _cell_to_text("hello")
    assert text.plain == "hello"


def test_celltotext_preserves_rich_text_style() -> None:
    source = Text("bold", style="bold")
    result = _cell_to_text(source)
    assert result.plain == "bold"
    assert "bold" in str(result.style)


def test_celltotext_collapses_newlines_to_spaces() -> None:
    text = _cell_to_text("line1\nline2")
    assert "\n" not in text.plain
    assert text.plain == "line1 line2"


def test_celltotext_flattens_renderables_via_capture() -> None:
    text = _cell_to_text(Notice.info("hi"))
    assert "hi" in text.plain


def test_framedviewer_constructor_accepts_minimum_args() -> None:
    viewer = FramedViewer(
        header_renderables=(),
        expandable_renderables=(),
        title="Empty",
        columns=(DataColumn(header="A"),),
        rows=(),
        footer_renderables=(),
    )
    assert viewer.title == "Empty"
    assert viewer.rows == ()


def test_framedviewer_is_frozen() -> None:
    viewer = FramedViewer(
        header_renderables=(),
        expandable_renderables=(),
        title="Demo",
        columns=(DataColumn(header="A"),),
        rows=(("hello",),),
        footer_renderables=(),
    )
    with pytest.raises(ValueError, match="frozen"):
        viewer.title = "Other"


def test_framedviewer_rejects_extra_fields() -> None:
    payload = {
        "header_renderables": (),
        "expandable_renderables": (),
        "title": "Demo",
        "columns": (DataColumn(header="A"),),
        "rows": (),
        "footer_renderables": (),
        "unknown_field": 42,
    }
    with pytest.raises(ValueError, match="Extra inputs"):
        FramedViewer.model_validate(payload)


def test_framedviewer_accepts_rich_text_cells() -> None:
    viewer = FramedViewer(
        header_renderables=(),
        expandable_renderables=(),
        title="Demo",
        columns=(DataColumn(header="A"),),
        rows=((Text("styled"),),),
        footer_renderables=(),
    )
    assert isinstance(viewer.rows[0][0], Text)
