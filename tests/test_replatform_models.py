# tests/test_replatform_models.py
# Tests for the replatform domain models (Story 01).
# Author: Pierre Grothe
# Date: 2026-06-29

"""Behavioral tests for nexus.replatform.models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.replatform.models import (
    ChecklistItem,
    ChecklistKind,
    ChecklistStatus,
    MigrationChecklist,
    UseCase,
    UseCaseInventory,
    WorkflowRef,
)

_TS = datetime(2026, 6, 29, 12, 0, 0, tzinfo=UTC)


def _workflow_ref() -> WorkflowRef:
    return WorkflowRef(
        key="x_acme_app|sys_hub_flow|create incident",
        name="Create Incident",
        type="sys_hub_flow",
        scope="x_acme_app",
    )


def test_workflow_ref_holds_fields() -> None:
    ref = _workflow_ref()
    assert ref.key == "x_acme_app|sys_hub_flow|create incident"
    assert ref.name == "Create Incident"
    assert ref.type == "sys_hub_flow"
    assert ref.scope == "x_acme_app"


def test_workflow_ref_is_frozen() -> None:
    ref = _workflow_ref()
    with pytest.raises(ValidationError):
        setattr(ref, "name", "changed")


def test_workflow_ref_forbids_extra() -> None:
    with pytest.raises(ValidationError):
        WorkflowRef.model_validate(
            {"key": "k", "name": "n", "type": "t", "scope": "s", "extra": "x"}
        )


def test_use_case_holds_workflows_and_evidence() -> None:
    uc = UseCase(
        key="x_acme_app",
        name="ITSM",
        domain="IT Service Management",
        workflows=(_workflow_ref(),),
        evidence=("x_acme_app",),
    )
    assert uc.domain == "IT Service Management"
    assert uc.workflows[0].name == "Create Incident"
    assert uc.evidence == ("x_acme_app",)


def test_use_case_evidence_defaults_empty() -> None:
    uc = UseCase(key="k", name="n", domain="d", workflows=())
    assert uc.evidence == ()


def test_use_case_inventory_holds_use_cases() -> None:
    inv = UseCaseInventory(
        profile="prod",
        captured_at=_TS,
        coverage=("ai_automation",),
        use_cases=(),
    )
    assert inv.profile == "prod"
    assert inv.coverage == ("ai_automation",)
    assert inv.use_cases == ()


def test_use_case_inventory_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError):
        UseCaseInventory(
            profile="prod",
            captured_at=datetime(2026, 6, 29, 12, 0, 0),  # naive -- no tzinfo
            coverage=(),
            use_cases=(),
        )


def test_checklist_status_values_match_names() -> None:
    assert ChecklistStatus.TODO == "TODO"
    assert ChecklistStatus.DONE == "DONE"
    assert ChecklistStatus.PARTIAL == "PARTIAL"
    assert ChecklistStatus.EXTRA == "EXTRA"


def test_checklist_kind_values_match_names() -> None:
    assert ChecklistKind.USE_CASE == "USE_CASE"
    assert ChecklistKind.WORKFLOW == "WORKFLOW"


def test_checklist_item_workflow_kind_is_valid() -> None:
    item = ChecklistItem(
        key="x_acme_app|sys_hub_flow|create incident",
        name="Create Incident",
        domain="IT Service Management",
        use_case_key="x_acme_app",
        kind=ChecklistKind.WORKFLOW,
        status=ChecklistStatus.TODO,
    )
    assert item.built_count is None
    assert item.total_count is None


def test_checklist_item_use_case_kind_is_valid() -> None:
    item = ChecklistItem(
        key="x_acme_app",
        name="ITSM",
        domain="IT Service Management",
        use_case_key="x_acme_app",
        kind=ChecklistKind.USE_CASE,
        status=ChecklistStatus.PARTIAL,
        built_count=2,
        total_count=5,
    )
    assert item.built_count == 2
    assert item.total_count == 5


def test_checklist_item_workflow_kind_rejects_counts() -> None:
    with pytest.raises(ValidationError):
        ChecklistItem(
            key="k",
            name="n",
            domain="d",
            use_case_key="u",
            kind=ChecklistKind.WORKFLOW,
            status=ChecklistStatus.DONE,
            built_count=1,
            total_count=1,
        )


def test_checklist_item_use_case_kind_requires_counts() -> None:
    with pytest.raises(ValidationError):
        ChecklistItem(
            key="k",
            name="n",
            domain="d",
            use_case_key="u",
            kind=ChecklistKind.USE_CASE,
            status=ChecklistStatus.TODO,
        )


def test_checklist_item_use_case_rejects_built_exceeding_total() -> None:
    with pytest.raises(ValidationError):
        ChecklistItem(
            key="k",
            name="n",
            domain="d",
            use_case_key="u",
            kind=ChecklistKind.USE_CASE,
            status=ChecklistStatus.PARTIAL,
            built_count=6,
            total_count=5,
        )


def test_checklist_item_use_case_rejects_negative_count() -> None:
    with pytest.raises(ValidationError):
        ChecklistItem(
            key="k",
            name="n",
            domain="d",
            use_case_key="u",
            kind=ChecklistKind.USE_CASE,
            status=ChecklistStatus.TODO,
            built_count=-1,
            total_count=0,
        )


def test_migration_checklist_holds_items() -> None:
    item = ChecklistItem(
        key="x_acme_app|sys_hub_flow|create incident",
        name="Create Incident",
        domain="IT Service Management",
        use_case_key="x_acme_app",
        kind=ChecklistKind.WORKFLOW,
        status=ChecklistStatus.TODO,
    )
    checklist = MigrationChecklist(
        source_profile="old",
        target_profile="new",
        source_captured_at=_TS,
        target_captured_at=_TS,
        coverage=("ai_automation",),
        items=(item,),
    )
    assert checklist.source_profile == "old"
    assert checklist.target_profile == "new"
    assert checklist.items[0].status is ChecklistStatus.TODO


def test_migration_checklist_is_frozen() -> None:
    checklist = MigrationChecklist(
        source_profile="old",
        target_profile="new",
        source_captured_at=_TS,
        target_captured_at=_TS,
        coverage=(),
        items=(),
    )
    with pytest.raises(ValidationError):
        checklist.source_profile = "x"  # type: ignore[misc]
