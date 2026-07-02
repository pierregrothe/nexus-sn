# tests/test_replatform_diff.py
# Tests for the bi-directional replatform checklist diff (Story 03).
# Author: Pierre Grothe
# Date: 2026-06-29

"""Behavioral tests for nexus.replatform.diff.build_checklist."""

from nexus.replatform.diff import build_checklist
from nexus.replatform.models import ChecklistItem, ChecklistKind, ChecklistStatus
from tests.fakes.replatform import make_use_case, make_use_case_inventory, make_workflow_ref


def _item(items: tuple[ChecklistItem, ...], *, key: str, kind: ChecklistKind) -> ChecklistItem:
    return next(i for i in items if i.key == key and i.kind is kind)


def test_build_checklist_marks_source_only_workflow_todo() -> None:
    alpha = make_workflow_ref(scope="x_app", name="Alpha")
    source = make_use_case_inventory(
        profile="old",
        use_cases=(make_use_case(key="x_app", domain="ITSM", workflows=(alpha,)),),
    )
    target = make_use_case_inventory(
        profile="new",
        use_cases=(make_use_case(key="x_app", domain="ITSM", workflows=()),),
    )
    checklist = build_checklist(source, target)
    assert _item(checklist.items, key=alpha.key, kind=ChecklistKind.WORKFLOW).status is (
        ChecklistStatus.TODO
    )


def test_build_checklist_marks_present_workflow_done() -> None:
    alpha = make_workflow_ref(scope="x_app", name="Alpha")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=(alpha,)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=(alpha,)),)
    )
    checklist = build_checklist(source, target)
    assert _item(checklist.items, key=alpha.key, kind=ChecklistKind.WORKFLOW).status is (
        ChecklistStatus.DONE
    )


def test_build_checklist_marks_target_only_workflow_extra() -> None:
    extra = make_workflow_ref(scope="x_app", name="Extra")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=()),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=(extra,)),)
    )
    checklist = build_checklist(source, target)
    assert _item(checklist.items, key=extra.key, kind=ChecklistKind.WORKFLOW).status is (
        ChecklistStatus.EXTRA
    )


def test_build_checklist_use_case_rollup_partial_with_fraction() -> None:
    a = make_workflow_ref(scope="x_app", name="Alpha")
    b = make_workflow_ref(scope="x_app", name="Beta")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=(a, b)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=(a,)),)
    )
    checklist = build_checklist(source, target)
    uc = _item(checklist.items, key="x_app", kind=ChecklistKind.USE_CASE)
    assert uc.status is ChecklistStatus.PARTIAL
    assert uc.built_count == 1
    assert uc.total_count == 2


def test_build_checklist_use_case_rollup_done_when_all_present() -> None:
    a = make_workflow_ref(scope="x_app", name="Alpha")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=(a,)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=(a,)),)
    )
    checklist = build_checklist(source, target)
    uc = _item(checklist.items, key="x_app", kind=ChecklistKind.USE_CASE)
    assert uc.status is ChecklistStatus.DONE
    assert uc.built_count == 1
    assert uc.total_count == 1


def test_build_checklist_use_case_rollup_todo_when_none_present() -> None:
    a = make_workflow_ref(scope="x_app", name="Alpha")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=(a,)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=()),)
    )
    checklist = build_checklist(source, target)
    uc = _item(checklist.items, key="x_app", kind=ChecklistKind.USE_CASE)
    assert uc.status is ChecklistStatus.TODO
    assert uc.built_count == 0
    assert uc.total_count == 1


def test_build_checklist_scope_alias_matches_renamed_scope() -> None:
    src_wf = make_workflow_ref(scope="x_oldcorp", name="Intake")
    tgt_wf = make_workflow_ref(scope="x_newcorp", name="Intake")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_oldcorp", workflows=(src_wf,)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_newcorp", workflows=(tgt_wf,)),)
    )
    checklist = build_checklist(source, target, aliases=(("x_oldcorp", "x_newcorp"),))
    assert _item(checklist.items, key=src_wf.key, kind=ChecklistKind.WORKFLOW).status is (
        ChecklistStatus.DONE
    )
    assert not any(i.status is ChecklistStatus.EXTRA for i in checklist.items)


def test_build_checklist_zero_workflow_source_use_case_is_done() -> None:
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=()),)
    )
    target = make_use_case_inventory(profile="new", use_cases=())
    checklist = build_checklist(source, target)
    uc = _item(checklist.items, key="x_app", kind=ChecklistKind.USE_CASE)
    assert uc.status is ChecklistStatus.DONE
    assert uc.built_count == 0
    assert uc.total_count == 0


def test_build_checklist_coverage_is_sorted_union() -> None:
    source = make_use_case_inventory(profile="old", coverage=("ai_automation",), use_cases=())
    target = make_use_case_inventory(
        profile="new", coverage=("developer_platform", "ai_automation"), use_cases=()
    )
    checklist = build_checklist(source, target)
    assert checklist.coverage == ("ai_automation", "developer_platform")


def test_build_checklist_items_are_stably_sorted() -> None:
    a = make_workflow_ref(scope="x_app", name="Alpha")
    b = make_workflow_ref(scope="x_app", name="Beta")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", domain="ITSM", workflows=(b, a)),)
    )
    target = make_use_case_inventory(profile="new", use_cases=())
    checklist = build_checklist(source, target)
    keys = [(i.domain, i.use_case_key, i.kind.value, i.key) for i in checklist.items]
    assert keys == sorted(keys)


def test_build_checklist_records_profiles_and_timestamps() -> None:
    source = make_use_case_inventory(profile="old", use_cases=())
    target = make_use_case_inventory(profile="new", use_cases=())
    checklist = build_checklist(source, target)
    assert checklist.source_profile == "old"
    assert checklist.target_profile == "new"
    assert checklist.source_captured_at == source.captured_at
    assert checklist.target_captured_at == target.captured_at


def test_build_checklist_duplicate_source_names_each_need_a_target() -> None:
    dup_a = make_workflow_ref(scope="x_app", name="Duplicate")
    dup_b = make_workflow_ref(scope="x_app", name="  duplicate ")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=(dup_a, dup_b)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=(dup_a,)),)
    )
    checklist = build_checklist(source, target)
    uc = _item(checklist.items, key="x_app", kind=ChecklistKind.USE_CASE)
    assert uc.status is ChecklistStatus.PARTIAL
    assert uc.built_count == 1
    assert uc.total_count == 2


def test_build_checklist_duplicate_target_names_surface_unmatched_extra() -> None:
    dup = make_workflow_ref(scope="x_app", name="Duplicate")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=(dup,)),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=(dup, dup)),)
    )
    checklist = build_checklist(source, target)
    extras = [i for i in checklist.items if i.status is ChecklistStatus.EXTRA]
    assert len(extras) == 1


def test_build_checklist_all_duplicate_targets_extra_when_source_missing() -> None:
    dup = make_workflow_ref(scope="x_app", name="Duplicate")
    source = make_use_case_inventory(
        profile="old", use_cases=(make_use_case(key="x_app", workflows=()),)
    )
    target = make_use_case_inventory(
        profile="new", use_cases=(make_use_case(key="x_app", workflows=(dup, dup)),)
    )
    checklist = build_checklist(source, target)
    extras = [i for i in checklist.items if i.status is ChecklistStatus.EXTRA]
    assert len(extras) == 2
