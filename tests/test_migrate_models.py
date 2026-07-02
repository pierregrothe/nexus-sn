# tests/test_migrate_models.py
# Tests for the migrate plan-file domain models (Story 02).
# Author: Pierre Grothe
# Date: 2026-07-02

"""Behavioral tests for nexus.migrate.models."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import nexus.migrate.models as migrate_models
import tests.fakes.migrate as fakes_migrate
from nexus.migrate.models import (
    Acknowledgment,
    BaselineEntry,
    DriftReport,
    FindingKind,
    IntegrityFinding,
    MigrationPlan,
    PlanItem,
    PlanLane,
    PreflightItemResult,
    PreflightReport,
    PreflightStatus,
    Selection,
    SelectionItem,
    Waiver,
    Wave,
    emit_plan_yaml,
    emit_selection_yaml,
    load_plan_yaml,
    load_selection_yaml,
)

__all__: list[str] = []

_TS = datetime(2026, 7, 2, 12, 0, 0, tzinfo=UTC)


def _selection_item() -> SelectionItem:
    return SelectionItem(key="x_alectri_core|sys_hub_flow|approve po", disposition="include")


def _selection() -> Selection:
    return Selection(
        source_profile="alectri",
        target_profile="retail",
        source_captured_at=_TS,
        items=(_selection_item(),),
    )


def _plan_item() -> PlanItem:
    return PlanItem(
        key="x_alectri_core|sys_hub_flow|approve po",
        lane=PlanLane.UPDATE_SET,
        wave_index=0,
    )


def _wave() -> Wave:
    return Wave(index=0, items=(_plan_item(),))


def _waiver(*, author: str = "alice", approver: str = "bob") -> Waiver:
    return Waiver(author=author, approver=approver, reason="manual post-migration step", date=_TS)


def _acknowledgment() -> Acknowledgment:
    return Acknowledgment(author="bob", reason="data seeded out of band", date=_TS)


def _integrity_finding_waived() -> IntegrityFinding:
    return IntegrityFinding(
        kind=FindingKind.STRANDED_DEPENDENCY,
        subject_key="x_alectri_core|sys_hub_flow|approve po",
        detail="references x_alectri_core|sys_db_object|po_request, which is excluded",
        waiver=_waiver(),
    )


def _integrity_finding_acknowledged() -> IntegrityFinding:
    return IntegrityFinding(
        kind=FindingKind.DATA_PREREQUISITE,
        subject_key="x_alectri_core|sys_db_object|po_request",
        detail="table data must be seeded before update set commit",
        acknowledgment=_acknowledgment(),
    )


def _migration_plan() -> MigrationPlan:
    return MigrationPlan(
        schema_version="1.0",
        source_profile="alectri",
        target_profile="retail",
        source_captured_at=_TS,
        target_captured_at=_TS,
        waves=(_wave(),),
        findings=(_integrity_finding_waived(), _integrity_finding_acknowledged()),
    )


# -- AC1: PlanLane -------------------------------------------------------


def test_plan_lane_members_exact_set() -> None:
    assert {member.value for member in PlanLane} == {
        "APP_REPO",
        "UPDATE_SET",
        "DATA",
        "MANUAL",
    }


# -- AC2: FindingKind -----------------------------------------------------


def test_finding_kind_includes_minimum_members() -> None:
    values = {member.value for member in FindingKind}
    assert {"STRANDED_DEPENDENCY", "DATA_PREREQUISITE", "CYCLE"} <= values


# -- AC3: Selection + SelectionItem ---------------------------------------


def test_selection_item_holds_fields_with_defaults() -> None:
    item = _selection_item()
    assert item.key == "x_alectri_core|sys_hub_flow|approve po"
    assert item.disposition == "include"
    assert item.annotation == ""
    assert item.annotated_by == ""


def test_selection_item_is_frozen() -> None:
    item = _selection_item()
    with pytest.raises(ValidationError):
        setattr(item, "disposition", "exclude")


def test_selection_item_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        SelectionItem.model_validate({"key": "k", "disposition": "include", "extra": "x"})


def test_selection_holds_items() -> None:
    selection = _selection()
    assert selection.source_profile == "alectri"
    assert selection.target_profile == "retail"
    assert selection.source_captured_at == _TS
    assert selection.items == (_selection_item(),)


def test_selection_is_frozen() -> None:
    selection = _selection()
    with pytest.raises(ValidationError):
        setattr(selection, "source_profile", "changed")


def test_selection_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        Selection.model_validate(
            {
                "source_profile": "alectri",
                "target_profile": "retail",
                "source_captured_at": _TS,
                "items": (),
                "extra": "x",
            }
        )


# -- AC4: PlanItem ----------------------------------------------------------


def test_plan_item_holds_fields_with_defaults() -> None:
    item = _plan_item()
    assert item.key == "x_alectri_core|sys_hub_flow|approve po"
    assert item.lane is PlanLane.UPDATE_SET
    assert item.added_by_closure is False
    assert item.wave_index == 0


def test_plan_item_is_frozen() -> None:
    item = _plan_item()
    with pytest.raises(ValidationError):
        setattr(item, "wave_index", 1)


def test_plan_item_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        PlanItem.model_validate(
            {"key": "k", "lane": PlanLane.MANUAL, "wave_index": 0, "extra": "x"}
        )


def test_plan_item_rejects_negative_wave_index() -> None:
    with pytest.raises(ValidationError):
        PlanItem(key="k", lane=PlanLane.MANUAL, wave_index=-1)


# -- AC5: IntegrityFinding --------------------------------------------------


def test_integrity_finding_defaults_waiver_and_acknowledgment_to_none() -> None:
    finding = IntegrityFinding(kind=FindingKind.CYCLE, subject_key="k", detail="cycle detected")
    assert finding.waiver is None
    assert finding.acknowledgment is None


def test_integrity_finding_holds_waiver() -> None:
    finding = _integrity_finding_waived()
    assert finding.kind is FindingKind.STRANDED_DEPENDENCY
    assert finding.waiver is not None
    assert finding.waiver.author == "alice"


def test_integrity_finding_holds_acknowledgment() -> None:
    finding = _integrity_finding_acknowledged()
    assert finding.kind is FindingKind.DATA_PREREQUISITE
    assert finding.acknowledgment is not None
    assert finding.acknowledgment.author == "bob"


def test_integrity_finding_is_frozen() -> None:
    finding = _integrity_finding_waived()
    with pytest.raises(ValidationError):
        setattr(finding, "detail", "changed")


def test_integrity_finding_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        IntegrityFinding.model_validate(
            {
                "kind": FindingKind.CYCLE,
                "subject_key": "k",
                "detail": "d",
                "extra": "x",
            }
        )


# -- AC6: Waiver segregation-of-duties table --------------------------------


def test_waiver_valid_when_approver_differs_from_author() -> None:
    waiver = _waiver(author="alice", approver="bob")
    assert waiver.author == "alice"
    assert waiver.approver == "bob"


def test_waiver_rejects_self_approval() -> None:
    with pytest.raises(ValidationError):
        _waiver(author="alice", approver="alice")


def test_waiver_is_frozen() -> None:
    waiver = _waiver()
    with pytest.raises(ValidationError):
        setattr(waiver, "reason", "changed")


def test_waiver_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        Waiver.model_validate(
            {"author": "alice", "approver": "bob", "reason": "r", "date": _TS, "extra": "x"}
        )


# -- AC7: Acknowledgment -----------------------------------------------------


def test_acknowledgment_holds_fields() -> None:
    ack = _acknowledgment()
    assert ack.author == "bob"
    assert ack.reason == "data seeded out of band"
    assert ack.date == _TS


def test_acknowledgment_is_frozen() -> None:
    ack = _acknowledgment()
    with pytest.raises(ValidationError):
        setattr(ack, "author", "changed")


def test_acknowledgment_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        Acknowledgment.model_validate({"author": "bob", "reason": "r", "date": _TS, "extra": "x"})


# -- AC8: Wave ----------------------------------------------------------------


def test_wave_holds_items() -> None:
    wave = _wave()
    assert wave.index == 0
    assert wave.items == (_plan_item(),)


def test_wave_rejects_negative_index() -> None:
    with pytest.raises(ValidationError):
        Wave(index=-1, items=())


def test_wave_is_frozen() -> None:
    wave = _wave()
    with pytest.raises(ValidationError):
        setattr(wave, "index", 1)


def test_wave_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        Wave.model_validate({"index": 0, "items": (), "extra": "x"})


# -- AC9: MigrationPlan -------------------------------------------------------


def test_migration_plan_holds_fields_with_defaults() -> None:
    plan = _migration_plan()
    assert plan.schema_version == "1.0"
    assert plan.source_profile == "alectri"
    assert plan.target_profile == "retail"
    assert plan.approved_by == ""
    assert plan.approved_at is None
    assert plan.target_chain == ()


def test_migration_plan_is_frozen() -> None:
    plan = _migration_plan()
    with pytest.raises(ValidationError):
        setattr(plan, "approved_by", "changed")


def test_migration_plan_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        MigrationPlan.model_validate(
            {
                "schema_version": "1.0",
                "source_profile": "alectri",
                "target_profile": "retail",
                "source_captured_at": _TS,
                "target_captured_at": _TS,
                "waves": (),
                "findings": (),
                "extra": "x",
            }
        )


# -- AC12: BaselineEntry + DriftReport (Story 06) -----------------------------


def _baseline_entry() -> BaselineEntry:
    return BaselineEntry(
        key="x_alectri_core|sys_hub_flow|approve po", fingerprint="2026-07-01 10:00:00"
    )


def test_baseline_entry_holds_fields_with_default_fingerprint() -> None:
    entry = BaselineEntry(key="k")
    assert entry.key == "k"
    assert entry.fingerprint == ""


def test_baseline_entry_is_frozen() -> None:
    entry = _baseline_entry()
    with pytest.raises(ValidationError):
        setattr(entry, "fingerprint", "changed")


def test_baseline_entry_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        BaselineEntry.model_validate({"key": "k", "fingerprint": "f", "extra": "x"})


def test_drift_report_defaults_to_no_drift() -> None:
    assert DriftReport().has_drift is False


def test_drift_report_has_drift_true_when_any_field_populated() -> None:
    assert DriftReport(source_added=("k",)).has_drift is True
    assert DriftReport(source_removed=("k",)).has_drift is True
    assert DriftReport(source_changed=("k",)).has_drift is True
    assert DriftReport(target_added=("k",)).has_drift is True
    assert DriftReport(target_removed=("k",)).has_drift is True
    assert DriftReport(target_changed=("k",)).has_drift is True


def test_drift_report_is_frozen() -> None:
    report = DriftReport()
    with pytest.raises(ValidationError):
        setattr(report, "source_added", ("k",))


def test_drift_report_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        DriftReport.model_validate({"source_added": (), "extra": "x"})


def test_migration_plan_defaults_baselines_to_empty() -> None:
    plan = _migration_plan()
    assert plan.source_baseline == ()
    assert plan.target_baseline == ()


# -- Story 07: PreflightStatus / PreflightItemResult / PreflightReport -------


def test_preflight_status_members_exact_set() -> None:
    assert {member.value for member in PreflightStatus} == {"PASS", "FAIL", "UNKNOWN"}


def _preflight_item_result() -> PreflightItemResult:
    return PreflightItemResult(
        item="cicd-plugin",
        instance="old",
        status=PreflightStatus.PASS,
        purpose="CICD plugin must be installed and active",
        remediation="Install and activate the CICD Spoke plugin",
    )


def test_preflight_item_result_holds_fields_with_default_detail() -> None:
    result = _preflight_item_result()
    assert result.item == "cicd-plugin"
    assert result.instance == "old"
    assert result.status is PreflightStatus.PASS
    assert result.detail == ""


def test_preflight_item_result_is_frozen() -> None:
    result = _preflight_item_result()
    with pytest.raises(ValidationError):
        setattr(result, "status", PreflightStatus.FAIL)


def test_preflight_item_result_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        PreflightItemResult.model_validate(
            {
                "item": "cicd-plugin",
                "instance": "old",
                "status": PreflightStatus.PASS,
                "purpose": "p",
                "remediation": "r",
                "extra": "x",
            }
        )


def test_preflight_report_holds_items() -> None:
    result = _preflight_item_result()
    report = PreflightReport(items=(result,))
    assert report.items == (result,)


def test_preflight_report_is_frozen() -> None:
    report = PreflightReport(items=())
    with pytest.raises(ValidationError):
        setattr(report, "items", (_preflight_item_result(),))


def test_preflight_report_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        PreflightReport.model_validate({"items": (), "extra": "x"})


# -- AC10: byte-stable YAML round trip -----------------------------------------


def test_emit_plan_yaml_round_trip_byte_stable(tmp_path: Path) -> None:
    plan = _migration_plan()
    first = emit_plan_yaml(plan)

    assert "\r" not in first
    assert "waiver" in first
    assert "acknowledgment" in first

    path = tmp_path / "plan.yaml"
    path.write_bytes(first.encode("utf-8"))
    reloaded_text = path.read_bytes().decode("utf-8")

    reloaded_plan = load_plan_yaml(reloaded_text)
    second = emit_plan_yaml(reloaded_plan)

    assert second == first
    assert "\r" not in second


def test_emit_plan_yaml_round_trip_with_baselines_byte_stable(tmp_path: Path) -> None:
    plan = MigrationPlan(
        schema_version="1.0",
        source_profile="alectri",
        target_profile="retail",
        source_captured_at=_TS,
        target_captured_at=_TS,
        waves=(_wave(),),
        findings=(),
        source_baseline=(_baseline_entry(),),
        target_baseline=(
            BaselineEntry(
                key="x_alectri_core|sys_hub_flow|approve po", fingerprint="2026-07-01 09:00:00"
            ),
        ),
    )
    first = emit_plan_yaml(plan)

    assert "source_baseline" in first
    assert "target_baseline" in first

    path = tmp_path / "plan.yaml"
    path.write_bytes(first.encode("utf-8"))
    reloaded = load_plan_yaml(path.read_bytes().decode("utf-8"))
    second = emit_plan_yaml(reloaded)

    assert second == first
    assert reloaded.source_baseline == plan.source_baseline
    assert reloaded.target_baseline == plan.target_baseline


def test_load_plan_yaml_old_plan_without_baseline_loads() -> None:
    # Story 05 plan files predate source_baseline/target_baseline -- a plan
    # YAML with no baseline keys at all must still load, defaulting both to
    # () (Story 06 Resolution 1).
    text = (
        "schema_version: '1.0'\n"
        "source_profile: alectri\n"
        "target_profile: retail\n"
        "source_captured_at: '2026-07-02T12:00:00+00:00'\n"
        "target_captured_at: '2026-07-02T12:00:00+00:00'\n"
        "waves: []\n"
        "findings: []\n"
    )

    plan = load_plan_yaml(text)

    assert plan.source_baseline == ()
    assert plan.target_baseline == ()


def test_load_plan_yaml_rejects_invalid_yaml_syntax() -> None:
    with pytest.raises(ValueError, match="not valid YAML"):
        load_plan_yaml("foo: [unclosed\n")


def test_load_plan_yaml_rejects_non_mapping() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        load_plan_yaml("- just\n- a list\n")


def test_emit_selection_yaml_round_trip_byte_stable(tmp_path: Path) -> None:
    selection = _selection()
    first = emit_selection_yaml(selection)

    assert "\r" not in first
    assert "include" in first

    path = tmp_path / "selection.yaml"
    path.write_bytes(first.encode("utf-8"))
    reloaded_text = path.read_bytes().decode("utf-8")

    reloaded_selection = load_selection_yaml(reloaded_text)
    second = emit_selection_yaml(reloaded_selection)

    assert second == first
    assert "\r" not in second


def test_load_selection_yaml_rejects_invalid_yaml_syntax() -> None:
    with pytest.raises(ValueError, match="not valid YAML"):
        load_selection_yaml("foo: [unclosed\n")


def test_load_selection_yaml_rejects_non_mapping() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        load_selection_yaml("- just\n- a list\n")


def test_make_selection_round_trips_byte_stable() -> None:
    selection = fakes_migrate.make_selection(
        items=(
            fakes_migrate.make_selection_item(
                key="x_alectri_core|sys_hub_flow|approve po", disposition="undecided"
            ),
        )
    )
    first = emit_selection_yaml(selection)
    assert emit_selection_yaml(load_selection_yaml(first)) == first


# -- AC11: exports + purity -----------------------------------------------------


def test_migrate_models_all_lists_every_public_name() -> None:
    # Story 07: PreflightStatus/PreflightItemResult/PreflightReport added --
    # see that story's report for why the exact-set assertion needed updating.
    assert set(migrate_models.__all__) == {
        "Acknowledgment",
        "BaselineEntry",
        "DriftReport",
        "FindingKind",
        "IntegrityFinding",
        "MigrationPlan",
        "PlanItem",
        "PlanLane",
        "PreflightItemResult",
        "PreflightReport",
        "PreflightStatus",
        "Selection",
        "SelectionItem",
        "Waiver",
        "Wave",
        "emit_plan_yaml",
        "emit_selection_yaml",
        "load_plan_yaml",
        "load_selection_yaml",
    }


def test_migrate_models_has_no_forbidden_imports_or_dict_any() -> None:
    source = Path(str(migrate_models.__file__)).read_text(encoding="utf-8")
    assert "nexus.cli" not in source
    assert "nexus.agents" not in source
    assert "nexus.replatform" not in source
    assert "dict[str, Any]" not in source


def test_make_migration_plan_round_trips_byte_stable() -> None:
    plan = fakes_migrate.make_migration_plan()
    first = emit_plan_yaml(plan)
    assert emit_plan_yaml(load_plan_yaml(first)) == first


def test_make_selection_constructs_selection_with_items() -> None:
    selection = fakes_migrate.make_selection()
    assert isinstance(selection, Selection)
    assert selection.items
