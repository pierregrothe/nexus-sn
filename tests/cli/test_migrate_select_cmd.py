# tests/cli/test_migrate_select_cmd.py
# Tests for `nexus migrate select` (Story 03).
# Author: Pierre Grothe
# Date: 2026-07-02

"""End-to-end CliRunner tests for `nexus migrate select`.

Writes a MigrationChecklist JSON file to tmp_path the same way
`nexus assess inventory --out` dumps its model (``model_dump_json(indent=2)``
via ``write_bytes``), then runs `select` against it and inspects the emitted
Selection YAML.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from nexus.cli.apps import app
from nexus.migrate.models import emit_selection_yaml, load_selection_yaml
from nexus.replatform.models import (
    ChecklistItem,
    ChecklistKind,
    ChecklistStatus,
    MigrationChecklist,
)
from tests.fakes.migrate import make_selection, make_selection_item

__all__: list[str] = []

_TS = datetime(2026, 7, 2, 12, 0, 0, tzinfo=UTC)


def _use_case_item(
    *,
    key: str = "x_acme_app",
    status: ChecklistStatus = ChecklistStatus.TODO,
    built_count: int = 0,
    total_count: int = 2,
) -> ChecklistItem:
    return ChecklistItem(
        key=key,
        name="Acme App",
        domain="ITSM",
        use_case_key=key,
        kind=ChecklistKind.USE_CASE,
        status=status,
        built_count=built_count,
        total_count=total_count,
    )


def _workflow_item(
    *,
    key: str = "x_acme_app|sys_hub_flow|approve po",
    use_case_key: str = "x_acme_app",
    status: ChecklistStatus = ChecklistStatus.TODO,
) -> ChecklistItem:
    return ChecklistItem(
        key=key,
        name="Approve PO",
        domain="ITSM",
        use_case_key=use_case_key,
        kind=ChecklistKind.WORKFLOW,
        status=status,
    )


def _checklist(items: tuple[ChecklistItem, ...]) -> MigrationChecklist:
    return MigrationChecklist(
        source_profile="old",
        target_profile="new",
        source_captured_at=_TS,
        target_captured_at=_TS,
        coverage=("ai_automation",),
        items=items,
    )


def _write_checklist(path: Path, checklist: MigrationChecklist) -> None:
    """Write a MigrationChecklist JSON file the same way assess --out does."""
    path.write_bytes(checklist.model_dump_json(indent=2).encode("utf-8"))


def _invoke_select(monkeypatch: pytest.MonkeyPatch, checklist_path: Path, out_path: Path) -> Result:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    return CliRunner().invoke(
        app,
        ["migrate", "select", "--from-checklist", str(checklist_path), "--out", str(out_path)],
    )


def test_migrate_select_seeds_every_checklist_item_undecided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checklist = _checklist((_use_case_item(), _workflow_item()))
    checklist_path = tmp_path / "checklist.json"
    _write_checklist(checklist_path, checklist)
    out_path = tmp_path / "selection.yaml"

    result = _invoke_select(monkeypatch, checklist_path, out_path)

    assert result.exit_code == 0
    selection = load_selection_yaml(out_path.read_text(encoding="utf-8"))
    assert len(selection.items) == len(checklist.items) == 2
    assert {item.key for item in selection.items} == {item.key for item in checklist.items}
    assert all(item.disposition == "undecided" for item in selection.items)
    assert all(item.annotation == "" for item in selection.items)
    assert all(item.annotated_by == "" for item in selection.items)


def test_migrate_select_dedupes_shared_key_across_kinds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_key = "x_acme_app"
    checklist = _checklist(
        (
            _use_case_item(key=shared_key),
            _workflow_item(key=shared_key, use_case_key=shared_key),
        )
    )
    checklist_path = tmp_path / "checklist.json"
    _write_checklist(checklist_path, checklist)
    out_path = tmp_path / "selection.yaml"

    result = _invoke_select(monkeypatch, checklist_path, out_path)

    assert result.exit_code == 0
    selection = load_selection_yaml(out_path.read_text(encoding="utf-8"))
    checklist_keys = {item.key for item in checklist.items}
    selection_keys = [item.key for item in selection.items]
    # set-equality...
    assert set(selection_keys) == checklist_keys
    # ...and exactly-once (not len(checklist.items), which double-counts the shared key).
    assert len(selection_keys) == len(checklist_keys) == 1


def test_migrate_select_seeds_done_and_extra_items_undecided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checklist = _checklist(
        (
            _use_case_item(
                key="x_done_app", status=ChecklistStatus.DONE, built_count=2, total_count=2
            ),
            _workflow_item(
                key="x_extra|sys_hub_flow|leftover",
                use_case_key="x_extra",
                status=ChecklistStatus.EXTRA,
            ),
        )
    )
    checklist_path = tmp_path / "checklist.json"
    _write_checklist(checklist_path, checklist)
    out_path = tmp_path / "selection.yaml"

    result = _invoke_select(monkeypatch, checklist_path, out_path)

    assert result.exit_code == 0
    selection = load_selection_yaml(out_path.read_text(encoding="utf-8"))
    assert len(selection.items) == 2
    assert all(item.disposition == "undecided" for item in selection.items)


def test_migrate_select_missing_checklist_file_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "absent.json"
    out_path = tmp_path / "selection.yaml"

    result = _invoke_select(monkeypatch, missing, out_path)

    assert result.exit_code == 1
    assert "cannot read checklist" in result.stderr
    assert not out_path.exists()


def test_migrate_select_non_utf8_checklist_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checklist_path = tmp_path / "checklist.json"
    checklist_path.write_bytes(b"\xff\xfe{invalid utf8: \x80\x81}")
    out_path = tmp_path / "selection.yaml"

    result = _invoke_select(monkeypatch, checklist_path, out_path)

    assert result.exit_code == 1
    assert "cannot read checklist" in result.stderr
    assert not out_path.exists()


def test_migrate_select_malformed_json_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checklist_path = tmp_path / "checklist.json"
    checklist_path.write_text("{not valid json", encoding="utf-8")
    out_path = tmp_path / "selection.yaml"

    result = _invoke_select(monkeypatch, checklist_path, out_path)

    assert result.exit_code == 1
    assert "not valid JSON" in result.stderr
    assert not out_path.exists()


def test_migrate_select_validation_failing_json_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Valid JSON, but missing every required MigrationChecklist field.
    checklist_path = tmp_path / "checklist.json"
    checklist_path.write_text('{"not_a_checklist": true}', encoding="utf-8")
    out_path = tmp_path / "selection.yaml"

    result = _invoke_select(monkeypatch, checklist_path, out_path)

    assert result.exit_code == 1
    assert "failed validation" in result.stderr
    assert not out_path.exists()


def test_migrate_select_writes_byte_stable_emit_selection_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checklist = _checklist((_use_case_item(), _workflow_item()))
    checklist_path = tmp_path / "checklist.json"
    _write_checklist(checklist_path, checklist)
    out_path = tmp_path / "selection.yaml"

    result = _invoke_select(monkeypatch, checklist_path, out_path)

    assert result.exit_code == 0
    written_text = out_path.read_text(encoding="utf-8")
    assert "\r" not in written_text

    expected_selection = make_selection(
        source_profile=checklist.source_profile,
        target_profile=checklist.target_profile,
        source_captured_at=checklist.source_captured_at,
        items=tuple(
            make_selection_item(key=item.key, disposition="undecided") for item in checklist.items
        ),
    )
    assert written_text == emit_selection_yaml(expected_selection)
