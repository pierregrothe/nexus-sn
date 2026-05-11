# tests/ui/components/test_notice.py
# Tests for Notice component.
# Author: Pierre Grothe
# Date: 2026-05-11

import io

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.notice import Notice
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def _record_console() -> Console:
    return Console(
        record=True,
        force_terminal=True,
        color_system="truecolor",
        theme=NEXUS_THEME,
        width=80,
    )


def test_notice_construction_holds_severity_and_message() -> None:
    notice = Notice(severity="error", message="Something broke")
    assert notice.severity == "error"
    assert notice.message == "Something broke"


def test_notice_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        Notice(severity="critical", message="x")  # type: ignore[arg-type]


def test_notice_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        Notice(severity="info", message="x", extra="y")  # type: ignore[call-arg]


def test_notice_is_frozen() -> None:
    notice = Notice(severity="info", message="x")
    with pytest.raises(ValidationError):
        notice.message = "y"  # type: ignore[misc]


def test_notice_error_classmethod_sets_severity() -> None:
    assert Notice.error("oops").severity == "error"


def test_notice_warn_classmethod_sets_severity() -> None:
    assert Notice.warn("careful").severity == "warn"


def test_notice_info_classmethod_sets_severity() -> None:
    assert Notice.info("hello").severity == "info"


def test_notice_error_renders_error_prefix_and_message() -> None:
    console = _record_console()
    console.print(Notice.error("Profile not found"))
    plain = console.export_text(styles=False)
    assert "Error: Profile not found" in plain


def test_notice_warn_renders_warning_prefix() -> None:
    console = _record_console()
    console.print(Notice.warn("Token expiring soon"))
    plain = console.export_text(styles=False)
    assert "Warning: Token expiring soon" in plain


def test_notice_info_renders_info_prefix() -> None:
    console = _record_console()
    console.print(Notice.info("Done"))
    plain = console.export_text(styles=False)
    assert "Info: Done" in plain


def test_notice_emits_distinct_ansi_per_severity() -> None:
    err_console = _record_console()
    err_console.print(Notice.error("x"))
    warn_console = _record_console()
    warn_console.print(Notice.warn("x"))
    err_styled = err_console.export_text(styles=True).replace("x", "")
    warn_styled = warn_console.export_text(styles=True).replace("x", "")
    assert err_styled != warn_styled
    assert "\x1b[" in err_styled
    assert "\x1b[" in warn_styled


def test_notice_renders_plain_when_not_terminal() -> None:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, theme=NEXUS_THEME, width=80)
    console.print(Notice.error("oops"))
    out = buffer.getvalue()
    assert "Error: oops" in out
    assert "\x1b[" not in out
