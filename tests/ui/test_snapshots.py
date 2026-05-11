# tests/ui/test_snapshots.py
# Cross-component visual snapshots for major rendered surfaces.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Cross-component visual snapshots for major rendered surfaces.

Each test renders a fixed input through the production component pipeline
and compares against a recorded text snapshot. When a render changes
intentionally, update the snapshot file in the same commit.
"""

import io
from pathlib import Path

from rich.console import Console

from nexus.ui import (
    CommandGuide,
    DataColumn,
    DataTable,
    KeyValuePanel,
    KvRow,
    StatusBadge,
)
from nexus.ui.theme import NEXUS_THEME

__all__: list[str] = []

_SNAPSHOTS = Path(__file__).parent / "snapshots"


def _record(width: int = 80) -> Console:
    return Console(
        file=io.StringIO(),
        record=True,
        force_terminal=True,
        color_system="truecolor",
        theme=NEXUS_THEME,
        width=width,
    )


def _assert_snapshot(name: str, console: Console) -> None:
    actual = console.export_text(styles=False)
    path = _SNAPSHOTS / name
    if not path.exists():
        path.write_text(actual, encoding="utf-8")
        return
    expected = path.read_text(encoding="utf-8")
    assert actual == expected, f"Snapshot drift for {name}. Update {path} if change is intentional."


def test_snapshot_status_dashboard_renders_identity_panel() -> None:
    console = _record()
    console.print(
        KeyValuePanel(
            title="Identity",
            rows=[
                KvRow(label="User", value="pierre@servicenow.com"),
                KvRow(label="Org", value="ServiceNow"),
                KvRow(label="Tier", value="PRO"),
                KvRow(label="Version", value="2026.05.1"),
                KvRow(
                    label="Servers",
                    value="3/4 ready",
                    suffix=StatusBadge.warn("1 need reauth"),
                ),
            ],
        )
    )
    _assert_snapshot("nexus_status.txt", console)


def test_snapshot_instance_list_and_guide_renders_table_and_commands() -> None:
    console = _record()
    console.print(
        DataTable(
            title="Instances",
            columns=[
                DataColumn(header="Profile", width=12),
                DataColumn(header="URL", width=30),
                DataColumn(header="Token", width=14),
            ],
            rows=[
                ["* prod", "acme.service-now.com", StatusBadge.ok("7h 30m")],
                ["  stage", "stage.service-now.com", StatusBadge.warn("14 min left")],
            ],
        )
    )
    console.print(
        CommandGuide(
            app_name="nexus instance",
            items=[
                ("register <profile>", "Add an instance"),
                ("connect [profile]", "Verify connection and refresh token"),
                ("list", "Show all registered instances"),
            ],
        )
    )
    _assert_snapshot("nexus_instance.txt", console)


def test_snapshot_capture_discover_table_renders_scope_counts() -> None:
    console = _record()
    console.print(
        DataTable(
            title="Custom scopes on prod",
            columns=[
                DataColumn(header="Scope Key", width=26),
                DataColumn(header="Name", width=20),
                DataColumn(header="Skl", width=5, justify="right"),
                DataColumn(header="Flow", width=5, justify="right"),
            ],
            rows=[
                ["x_snc_app", "ACME App", "3", "12"],
                ["x_snc_helper", "ACME Helper", "0", "5"],
            ],
        )
    )
    _assert_snapshot("nexus_capture_discover.txt", console)
