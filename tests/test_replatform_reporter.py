# tests/test_replatform_reporter.py
# Tests for the replatform checklist reporter (Story 04).
# Author: Pierre Grothe
# Date: 2026-06-29

"""Console + markdown rendering of a MigrationChecklist."""

from io import StringIO
from pathlib import Path

from rich.console import Console

from nexus.replatform.diff import build_checklist
from nexus.replatform.models import MigrationChecklist
from nexus.replatform.reporter import EMPTY_SOURCE_NOTICE, render_checklist, write_markdown
from nexus.ui.capabilities import ColorDepth, RenderProfile, TerminalCapabilities
from nexus.ui.render_context import RenderContext
from nexus.ui.theme import NEXUS_THEME
from tests.fakes.replatform import make_use_case, make_use_case_inventory, make_workflow_ref


def _ctx(profile: RenderProfile, buf: StringIO) -> RenderContext:
    console = Console(file=buf, width=120, record=True, theme=NEXUS_THEME, force_terminal=False)
    caps = TerminalCapabilities(
        is_tty=False,
        is_ci=False,
        color_depth=ColorDepth.NONE,
        cols=120,
        rows=40,
        legacy_windows=False,
        term_program="",
        is_dumb_terminal=False,
        is_multiplexer=False,
        no_color_env=False,
        forced_plain=profile is RenderProfile.PLAIN,
        supports_hyperlinks=False,
    )
    return RenderContext(console=console, caps=caps, profile=profile)


def _partial_checklist() -> MigrationChecklist:
    source = make_use_case_inventory(
        profile="old",
        use_cases=(
            make_use_case(
                key="x_app",
                domain="ITSM",
                workflows=(
                    make_workflow_ref(scope="x_app", name="Alpha"),
                    make_workflow_ref(scope="x_app", name="Beta"),
                ),
            ),
        ),
    )
    target = make_use_case_inventory(
        profile="new",
        use_cases=(
            make_use_case(
                key="x_app",
                domain="ITSM",
                workflows=(make_workflow_ref(scope="x_app", name="Alpha"),),
            ),
        ),
    )
    return build_checklist(source, target)


def _empty_checklist() -> MigrationChecklist:
    return build_checklist(
        make_use_case_inventory(profile="old", use_cases=()),
        make_use_case_inventory(profile="new", use_cases=()),
    )


def test_render_checklist_plain_lists_statuses() -> None:
    buf = StringIO()
    render_checklist(_partial_checklist(), _ctx(RenderProfile.PLAIN, buf))
    out = buf.getvalue()
    assert "Alpha" in out
    assert "Beta" in out
    assert "DONE" in out
    assert "TODO" in out
    assert "PARTIAL" in out


def test_render_checklist_rich_renders_without_error() -> None:
    buf = StringIO()
    ctx = _ctx(RenderProfile.RICH, buf)
    render_checklist(_partial_checklist(), ctx)
    text = ctx.console.export_text()
    assert "ITSM" in text
    assert "Alpha" in text


def test_render_checklist_empty_source_warns() -> None:
    buf = StringIO()
    render_checklist(_empty_checklist(), _ctx(RenderProfile.PLAIN, buf))
    assert "source inventory is empty" in buf.getvalue()


def test_render_checklist_rich_empty_source_warns() -> None:
    buf = StringIO()
    ctx = _ctx(RenderProfile.RICH, buf)
    render_checklist(_empty_checklist(), ctx)
    assert "source inventory is empty" in ctx.console.export_text()


def test_write_markdown_uses_task_checkboxes(tmp_path: Path) -> None:
    out = tmp_path / "checklist.md"
    write_markdown(_partial_checklist(), out)
    content = out.read_text(encoding="utf-8")
    assert "- [x]" in content
    assert "- [ ]" in content
    assert "1/2" in content


def test_write_markdown_is_byte_stable(tmp_path: Path) -> None:
    checklist = _partial_checklist()
    first = tmp_path / "a.md"
    second = tmp_path / "b.md"
    write_markdown(checklist, first)
    write_markdown(checklist, second)
    assert first.read_bytes() == second.read_bytes()
    assert b"\r\n" not in first.read_bytes()


def test_write_markdown_empty_source_includes_warning(tmp_path: Path) -> None:
    out = tmp_path / "empty.md"
    write_markdown(_empty_checklist(), out)
    assert EMPTY_SOURCE_NOTICE in out.read_text(encoding="utf-8")
