# tests/ui/components/test_badge.py
# Tests for the StatusBadge component.
# Author: Pierre Grothe
# Date: 2026-05-11

import io

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.badge import StatusBadge
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []


def _record_console() -> Console:
    return Console(
        file=io.StringIO(),
        record=True,
        force_terminal=True,
        color_system="truecolor",
        theme=NEXUS_THEME,
        width=40,
    )


def test_status_badge_construction_holds_text_and_variant() -> None:
    badge = StatusBadge(text="READY", variant="ok")
    assert badge.text == "READY"
    assert badge.variant == "ok"


def test_status_badge_rejects_unknown_variant() -> None:
    with pytest.raises(ValidationError):
        StatusBadge(text="READY", variant="nope")  # type: ignore[arg-type]


def test_status_badge_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        StatusBadge(text="READY", variant="ok", extra="x")  # type: ignore[call-arg]


def test_status_badge_is_frozen() -> None:
    badge = StatusBadge(text="READY", variant="ok")
    with pytest.raises(ValidationError):
        badge.text = "OTHER"


def test_status_badge_ok_classmethod_sets_variant() -> None:
    assert StatusBadge.ok("READY").variant == "ok"


def test_status_badge_warn_classmethod_sets_variant() -> None:
    assert StatusBadge.warn("NEEDS REAUTH").variant == "warn"


def test_status_badge_error_classmethod_sets_variant() -> None:
    assert StatusBadge.error("EXPIRED").variant == "error"


def test_status_badge_renders_text_in_terminal() -> None:
    console = _record_console()
    console.print(StatusBadge.ok("READY"))
    plain = console.export_text(styles=False)
    assert "READY" in plain


def test_status_badge_warn_emits_yellow_ansi() -> None:
    console_warn = _record_console()
    console_warn.print(StatusBadge.warn("NEEDS REAUTH"))
    warn_styled = console_warn.export_text(styles=True)

    console_ok = _record_console()
    console_ok.print(StatusBadge.ok("READY"))
    ok_styled = console_ok.export_text(styles=True)

    assert "NEEDS REAUTH" in warn_styled
    assert "\x1b[" in warn_styled
    # Different variants must emit different ANSI sequences.
    assert warn_styled.replace("NEEDS REAUTH", "") != ok_styled.replace("READY", "")


def test_status_badge_renders_plain_when_not_terminal() -> None:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, theme=NEXUS_THEME, width=40)
    console.print(StatusBadge.error("EXPIRED"))
    output = buffer.getvalue()
    assert "EXPIRED" in output
    assert "\x1b[" not in output
