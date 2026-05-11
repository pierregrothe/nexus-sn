# tests/ui/components/test_panel.py
# Tests for KvRow, KeyValuePanel, two_col.
# Author: Pierre Grothe
# Date: 2026-05-11

import io

import pytest
from pydantic import ValidationError
from rich.console import Console

from nexus.ui.components.badge import StatusBadge
from nexus.ui.components.panel import KeyValuePanel, KvRow, two_col
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


def test_kvrow_construction_holds_label_value() -> None:
    row = KvRow(label="User", value="pierre@servicenow.com")
    assert row.label == "User"
    assert row.value == "pierre@servicenow.com"


def test_kvrow_suffix_defaults_to_none() -> None:
    assert KvRow(label="User", value="x").suffix is None


def test_kvrow_accepts_renderable_value() -> None:
    badge = StatusBadge.error("EXPIRED")
    row = KvRow(label="Token", value=badge)
    assert row.value is badge


def test_kvrow_accepts_renderable_suffix() -> None:
    badge = StatusBadge.warn("1 need reauth")
    row = KvRow(label="Servers", value="3/4 ready", suffix=badge)
    assert row.suffix is badge


def test_kvrow_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        KvRow(label="x", value="y", extra="z")  # type: ignore[call-arg]


def test_kvrow_is_frozen() -> None:
    row = KvRow(label="x", value="y")
    with pytest.raises(ValidationError):
        row.label = "z"


def test_keyvaluepanel_renders_title_and_rows() -> None:
    console = _record_console()
    console.print(
        KeyValuePanel(
            title="Identity",
            rows=[
                KvRow(label="User", value="pierre@servicenow.com"),
                KvRow(label="Tier", value="PRO"),
            ],
        )
    )
    plain = console.export_text(styles=False)
    assert "Identity" in plain
    assert "User:" in plain
    assert "pierre@servicenow.com" in plain
    assert "Tier:" in plain
    assert "PRO" in plain


def test_keyvaluepanel_pads_short_labels_to_match_longest() -> None:
    console = _record_console()
    console.print(
        KeyValuePanel(
            title="x",
            rows=[
                KvRow(label="A", value="1"),
                KvRow(label="LongerLabel", value="2"),
            ],
        )
    )
    plain = console.export_text(styles=False)
    # Both values should be vertically aligned -- find their column positions.
    lines = [ln for ln in plain.splitlines() if "1" in ln or "2" in ln]
    # Find rows that contain just one of the values
    one_line = next(ln for ln in lines if "1" in ln and "2" not in ln)
    two_line = next(ln for ln in lines if "2" in ln and "1" not in ln)
    assert one_line.index("1") == two_line.index("2")


def test_keyvaluepanel_renders_status_badge_value() -> None:
    console = _record_console()
    console.print(
        KeyValuePanel(
            title="Auth",
            rows=[KvRow(label="Token", value=StatusBadge.error("EXPIRED"))],
        )
    )
    plain = console.export_text(styles=False)
    assert "Token:" in plain
    assert "EXPIRED" in plain


def test_keyvaluepanel_renders_suffix_after_value() -> None:
    console = _record_console()
    console.print(
        KeyValuePanel(
            title="x",
            rows=[
                KvRow(
                    label="Servers",
                    value="3/4 ready",
                    suffix=StatusBadge.warn("1 need reauth"),
                )
            ],
        )
    )
    plain = console.export_text(styles=False)
    assert plain.index("3/4 ready") < plain.index("1 need reauth")


def test_keyvaluepanel_is_frozen() -> None:
    panel = KeyValuePanel(title="x", rows=[KvRow(label="a", value="b")])
    with pytest.raises(ValidationError):
        panel.title = "y"


def test_two_col_renders_both_panels_side_by_side() -> None:
    left = KeyValuePanel(title="L", rows=[KvRow(label="a", value="1")])
    right = KeyValuePanel(
        title="R",
        rows=[
            KvRow(label="a", value="1"),
            KvRow(label="b", value="2"),
            KvRow(label="c", value="3"),
        ],
    )
    console = _record_console(width=80)
    console.print(two_col(left, right))
    plain = console.export_text(styles=False)
    # Both panel titles must appear, all labels from the right must appear.
    assert "L" in plain
    assert "R" in plain
    assert "a:" in plain
    assert "b:" in plain
    assert "c:" in plain


def test_keyvaluepanel_renders_plain_when_not_terminal() -> None:
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        force_terminal=False,
        theme=NEXUS_THEME,
        width=80,
    )
    console.print(
        KeyValuePanel(
            title="x",
            rows=[KvRow(label="a", value="b")],
        )
    )
    out = buffer.getvalue()
    assert "a:" in out
    assert "b" in out
    assert "\x1b[" not in out
