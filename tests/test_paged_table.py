# tests/test_paged_table.py
# Tests for PagedTable rendering across four render profiles.
# Author: Pierre Grothe
# Date: 2026-05-15

"""Cover PagedTable dispatch + FakePager invocation."""

from io import StringIO

import pytest
from rich.console import Console
from rich.text import Text

from nexus.ui.capabilities import ColorDepth, RenderProfile, TerminalCapabilities
from nexus.ui.components.paged_table import PagedTable
from nexus.ui.components.table import DataColumn
from nexus.ui.render_context import RenderContext
from tests.fakes.pager import FakePager


def _make_caps(profile_hint: RenderProfile, rows: int = 40) -> TerminalCapabilities:
    return TerminalCapabilities(
        is_tty=profile_hint is not RenderProfile.PLAIN,
        is_ci=False,
        color_depth=ColorDepth.TRUECOLOR,
        cols=120,
        rows=rows,
        legacy_windows=False,
        term_program="",
        is_dumb_terminal=False,
        is_multiplexer=False,
        no_color_env=False,
        forced_plain=profile_hint is RenderProfile.PLAIN,
        supports_hyperlinks=True,
    )


def _make_render_context(profile: RenderProfile, rows: int = 40) -> tuple[RenderContext, StringIO]:
    buf = StringIO()
    console = Console(
        file=buf,
        force_terminal=profile is not RenderProfile.PLAIN,
        color_system="truecolor" if profile is RenderProfile.RICH else None,
        legacy_windows=False,
        width=120,
        record=False,
    )
    caps = _make_caps(profile, rows=rows)
    return RenderContext(console=console, caps=caps, profile=profile), buf


def _simple_table(row_count: int) -> PagedTable:
    return PagedTable(
        title="Demo",
        columns=(DataColumn(header="A"), DataColumn(header="B")),
        rows=tuple(("a" + str(i), "b" + str(i)) for i in range(row_count)),
    )


def test_render_rich_below_threshold_does_not_invoke_pager() -> None:
    ctx, _buf = _make_render_context(RenderProfile.RICH, rows=40)
    pager = FakePager()
    _simple_table(5).render(ctx, pager=pager)
    assert pager.call_count == 0


def test_render_rich_above_threshold_invokes_pager() -> None:
    ctx, _buf = _make_render_context(RenderProfile.RICH, rows=10)
    pager = FakePager()
    _simple_table(20).render(ctx, pager=pager)
    assert pager.call_count == 1
    assert pager.last_text is not None
    assert "a0" in pager.last_text
    assert "a19" in pager.last_text


def test_render_rich_without_pager_falls_back_inline() -> None:
    ctx, buf = _make_render_context(RenderProfile.RICH, rows=10)
    _simple_table(20).render(ctx, pager=None)
    output = buf.getvalue()
    assert "a0" in output
    assert "a19" in output


def test_render_basic_above_threshold_invokes_pager() -> None:
    ctx, _buf = _make_render_context(RenderProfile.BASIC, rows=10)
    pager = FakePager()
    _simple_table(20).render(ctx, pager=pager)
    assert pager.call_count == 1


def test_render_legacy_emits_inline_table_without_pager() -> None:
    ctx, buf = _make_render_context(RenderProfile.LEGACY, rows=10)
    pager = FakePager()
    _simple_table(20).render(ctx, pager=pager)
    output = buf.getvalue()
    assert pager.call_count == 0
    assert "a0" in output
    assert "a19" in output


def test_render_plain_emits_tab_separated_rows() -> None:
    ctx, buf = _make_render_context(RenderProfile.PLAIN, rows=24)
    pager = FakePager()
    _simple_table(3).render(ctx, pager=pager)
    output = buf.getvalue()
    assert pager.call_count == 0
    lines = [line for line in output.splitlines() if line]
    assert lines[0] == "A\tB"
    assert lines[1] == "a0\tb0"
    assert lines[2] == "a1\tb1"
    assert lines[3] == "a2\tb2"


def test_render_plain_renders_renderable_cell_to_plain_string() -> None:
    ctx, buf = _make_render_context(RenderProfile.PLAIN, rows=24)
    table = PagedTable(
        title="Demo",
        columns=(DataColumn(header="Name"), DataColumn(header="State")),
        rows=((Text("hello", style="bold"), "ready"),),
    )
    table.render(ctx, pager=None)
    output = buf.getvalue()
    assert "hello\tready" in output
    assert "\x1b[" not in output


def test_render_plain_with_no_pager_works() -> None:
    ctx, buf = _make_render_context(RenderProfile.PLAIN, rows=24)
    _simple_table(2).render(ctx, pager=None)
    assert "A\tB" in buf.getvalue()


def test_pagedtable_is_frozen() -> None:
    table = _simple_table(1)
    with pytest.raises(ValueError, match="frozen"):
        table.title = "Other"
