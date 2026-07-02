# tests/cli/test_migrate_plan_cmd.py
# Tests for `nexus migrate plan` (story 05b).
# Author: Pierre Grothe
# Date: 2026-07-02

"""End-to-end CliRunner tests for `nexus migrate plan`.

Monkeypatches ``commands_migrate.default_plan_collaborators`` with a
fixture-driven ``PlanCollaborators`` (same pattern as
``test_assess_replatform_cmd.py``'s ``default_replatform_collaborators``
monkeypatching) so no live ServiceNow call is ever made -- the production
wiring itself is ``# pragma: no cover``.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from nexus.capture.models import CaptureResult
from nexus.cli import commands_migrate
from nexus.cli.apps import app
from nexus.cli.commands_migrate import PlanCollaborators
from nexus.connectors.servicenow.errors import SNClientError
from nexus.migrate.models import Selection, emit_selection_yaml, load_plan_yaml
from nexus.schema.models import SchemaGraph
from tests.fakes.migrate import make_selection, make_selection_item
from tests.fakes.migrate_closure import (
    make_capture,
    make_record,
    make_ref,
    make_reference_edge,
    make_schema_graph,
)

_SCOPE = "x_acme_app"


def _happy_selection() -> Selection:
    return make_selection(
        items=(
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
        ),
    )


def _happy_captures() -> tuple[CaptureResult, ...]:
    record = make_record("sys_script_include", "a1", _SCOPE, "Helper A")
    source = make_capture((record,), instance_id="alectri")
    target = make_capture((), instance_id="retail")
    return (source, target)


def _unapproved_selection() -> Selection:
    return make_selection(
        items=(
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper b", disposition="exclude"),
        ),
    )


def _unapproved_captures() -> tuple[CaptureResult, ...]:
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", uses=make_ref("b1", "Helper B")
    )
    record_b = make_record("sys_script_include", "b1", _SCOPE, "Helper B")
    source = make_capture((record_a, record_b), instance_id="alectri")
    target = make_capture((), instance_id="retail")
    return (source, target)


def _unapproved_schema_graph() -> SchemaGraph:
    return make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include"),)
    )


def _write_selection(path: Path, selection: Selection) -> None:
    path.write_bytes(emit_selection_yaml(selection).encode("utf-8"))


def _set_collaborators(
    monkeypatch: pytest.MonkeyPatch,
    *,
    captures: tuple[CaptureResult, ...],
    schema_graph: SchemaGraph,
) -> None:
    def fake_factory() -> PlanCollaborators:
        return PlanCollaborators(
            build_captures=lambda _selection: captures,
            build_schema_graph=lambda _selection: schema_graph,
        )

    monkeypatch.setattr(commands_migrate, "default_plan_collaborators", fake_factory)


def _invoke_plan(selection_path: Path, out_path: Path) -> Result:
    return CliRunner().invoke(
        app, ["migrate", "plan", "--selection", str(selection_path), "--out", str(out_path)]
    )


# -- AC1: success writes runbook.md + runbook.plan.yaml, exit 0 --------------


def test_migrate_plan_writes_runbook_and_plan_yaml_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    selection_path = tmp_path / "selection.yaml"
    _write_selection(selection_path, _happy_selection())
    _set_collaborators(monkeypatch, captures=_happy_captures(), schema_graph=make_schema_graph())
    out_path = tmp_path / "runbook.md"

    result = _invoke_plan(selection_path, out_path)

    assert result.exit_code == 0
    assert out_path.exists()
    assert "# Migration Runbook" in out_path.read_text(encoding="utf-8")
    plan_path = tmp_path / "runbook.plan.yaml"
    assert plan_path.exists()
    plan = load_plan_yaml(plan_path.read_text(encoding="utf-8"))
    assert plan.approved_by == ""
    assert plan.approved_at is None
    assert plan.source_profile == "alectri"
    assert plan.target_profile == "retail"


def test_migrate_plan_prints_console_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    selection_path = tmp_path / "selection.yaml"
    _write_selection(selection_path, _happy_selection())
    _set_collaborators(monkeypatch, captures=_happy_captures(), schema_graph=make_schema_graph())
    out_path = tmp_path / "runbook.md"

    result = _invoke_plan(selection_path, out_path)

    assert result.exit_code == 0
    assert "migration plan alectri -> retail" in result.output


def test_migrate_plan_records_fresh_source_capture_timestamp_not_selection_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression (story 05 review): run_plan used to copy the seed-time
    # selection.source_captured_at into the plan, silently discarding the
    # FRESH source capture's timestamp -- the value the plan was actually
    # computed from (ADR-026 Decision 4). Timestamps here are deliberately
    # DISTINCT: the selection's seed-time value is older than the fresh
    # source capture's.
    stale_seed_ts = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
    fresh_source_ts = datetime(2026, 7, 2, 15, 30, 0, tzinfo=UTC)
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    selection = make_selection(
        source_captured_at=stale_seed_ts,
        items=(
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
        ),
    )
    selection_path = tmp_path / "selection.yaml"
    _write_selection(selection_path, selection)
    record = make_record("sys_script_include", "a1", _SCOPE, "Helper A")
    source = make_capture((record,), instance_id="alectri", captured_at=fresh_source_ts)
    target = make_capture((), instance_id="retail")
    _set_collaborators(monkeypatch, captures=(source, target), schema_graph=make_schema_graph())
    out_path = tmp_path / "runbook.md"

    result = _invoke_plan(selection_path, out_path)

    assert result.exit_code == 0
    # The plan YAML carries the FRESH source capture timestamp...
    plan = load_plan_yaml((tmp_path / "runbook.plan.yaml").read_text(encoding="utf-8"))
    assert plan.source_captured_at == fresh_source_ts
    assert plan.source_captured_at != stale_seed_ts
    # ...and so does the runbook's freshness header.
    runbook = out_path.read_text(encoding="utf-8")
    assert f"Source snapshot: alectri captured_at={fresh_source_ts.isoformat()}" in runbook
    assert stale_seed_ts.isoformat() not in runbook


# -- AC7: unapproved plan still writes and exits 0 ----------------------------


def test_migrate_plan_unapproved_plan_still_writes_and_exits_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    selection_path = tmp_path / "selection.yaml"
    _write_selection(selection_path, _unapproved_selection())
    _set_collaborators(
        monkeypatch, captures=_unapproved_captures(), schema_graph=_unapproved_schema_graph()
    )
    out_path = tmp_path / "runbook.md"

    result = _invoke_plan(selection_path, out_path)

    assert result.exit_code == 0
    assert out_path.exists()
    assert "NOT APPROVED" in out_path.read_text(encoding="utf-8")


# -- Selection file error paths exit 1 with stderr message -------------------


def test_migrate_plan_missing_selection_file_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    missing = tmp_path / "absent.yaml"
    out_path = tmp_path / "runbook.md"

    result = _invoke_plan(missing, out_path)

    assert result.exit_code == 1
    assert "cannot read selection" in result.stderr
    assert not out_path.exists()


def test_migrate_plan_non_mapping_selection_yaml_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    selection_path = tmp_path / "selection.yaml"
    selection_path.write_text("- a\n- b\n", encoding="utf-8")
    out_path = tmp_path / "runbook.md"

    result = _invoke_plan(selection_path, out_path)

    assert result.exit_code == 1
    assert "not valid YAML" in result.stderr
    assert not out_path.exists()


def test_migrate_plan_selection_failing_validation_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    selection_path = tmp_path / "selection.yaml"
    selection_path.write_text("not_a_selection: true\n", encoding="utf-8")
    out_path = tmp_path / "runbook.md"

    result = _invoke_plan(selection_path, out_path)

    assert result.exit_code == 1
    assert "failed validation" in result.stderr
    assert not out_path.exists()


# -- Collaborator failures surface as an error, not a traceback --------------


def test_migrate_plan_collaborator_capture_failure_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    selection_path = tmp_path / "selection.yaml"
    _write_selection(selection_path, _happy_selection())

    def fake_factory() -> PlanCollaborators:
        def _raise(_selection: Selection) -> tuple[CaptureResult, ...]:
            raise SNClientError("boom", status_code=500)

        return PlanCollaborators(
            build_captures=_raise,
            build_schema_graph=lambda _selection: make_schema_graph(),
        )

    monkeypatch.setattr(commands_migrate, "default_plan_collaborators", fake_factory)
    out_path = tmp_path / "runbook.md"

    result = _invoke_plan(selection_path, out_path)

    assert result.exit_code == 1
    assert "failed to capture instances for plan" in result.stderr
    assert not out_path.exists()


def test_migrate_plan_no_source_captures_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    selection_path = tmp_path / "selection.yaml"
    _write_selection(selection_path, _happy_selection())
    target_only = (make_capture((), instance_id="retail"),)
    _set_collaborators(monkeypatch, captures=target_only, schema_graph=make_schema_graph())
    out_path = tmp_path / "runbook.md"

    result = _invoke_plan(selection_path, out_path)

    assert result.exit_code == 1
    assert "no captured records found for source profile" in result.stderr
    assert not out_path.exists()


def test_migrate_plan_no_target_captures_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_AUTO_UPDATE", "0")
    selection_path = tmp_path / "selection.yaml"
    _write_selection(selection_path, _happy_selection())
    source_only = (make_capture((make_record("sys_script_include", "a1", _SCOPE, "Helper A"),)),)
    _set_collaborators(monkeypatch, captures=source_only, schema_graph=make_schema_graph())
    out_path = tmp_path / "runbook.md"

    result = _invoke_plan(selection_path, out_path)

    assert result.exit_code == 1
    assert "no captured records found for target profile" in result.stderr
    assert not out_path.exists()
