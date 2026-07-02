# tests/test_migrate_closure.py
# Tests for nexus.migrate.closure (story 04a): AC1-AC5.
# Author: Pierre Grothe
# Date: 2026-07-02

"""AC1-AC5: dependency-closure rule-table tests, one row per test.

No mocks; fixtures are hand-crafted CaptureResult/SchemaGraph pairs from
tests/fakes/migrate_closure.py, one rule at a time (not the full 30K-record
dataset -- that measurement is Story 00's job).
"""

from pathlib import Path

import pytest

from nexus.capture.models import CaptureResult
from nexus.migrate.closure import DEFAULT_STOP_LIST, build_closure, load_stop_list
from nexus.migrate.models import FindingKind, Selection, SelectionItem
from tests.fakes.migrate import make_selection, make_selection_item
from tests.fakes.migrate_closure import (
    make_capture,
    make_record,
    make_ref,
    make_reference_edge,
    make_schema_graph,
)

_SCOPE = "x_acme_app"
_OTHER_SCOPE = "x_other_app"


def _selection(items: tuple[SelectionItem, ...]) -> Selection:
    return make_selection(source_profile="alectri", target_profile="retail", items=items)


# -- DEFAULT_STOP_LIST -------------------------------------------------------


def test_default_stop_list_matches_story_00_seed() -> None:
    assert set(DEFAULT_STOP_LIST) == {"cmdb_ci", "sys_choice", "sys_user", "sys_user_group"}


# -- AC1: reference-field closure rule table ---------------------------------


def test_build_closure_records_edge_for_include_include_reference() -> None:
    selection = _selection(
        (
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper b", disposition="include"),
        )
    )
    record_a = make_record("sys_script_include", "a1", _SCOPE, "Helper A", uses="b1")
    record_b = make_record("sys_script_include", "b1", _SCOPE, "Helper B")
    captures = (make_capture((record_a, record_b), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include"),)
    )

    result = build_closure(selection, captures, schema_graph)

    assert {item.key for item in result.items} == {
        f"{_SCOPE}|sys_script_include|helper a",
        f"{_SCOPE}|sys_script_include|helper b",
    }
    assert not any(item.added_by_closure for item in result.items)
    assert len(result.edges) == 1
    assert result.edges[0].dependent_key == f"{_SCOPE}|sys_script_include|helper a"
    assert result.edges[0].dependency_key == f"{_SCOPE}|sys_script_include|helper b"
    assert result.findings == ()


def test_build_closure_auto_adds_undecided_reference_target() -> None:
    selection = _selection(
        (
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(
                key=f"{_SCOPE}|sys_script_include|helper b", disposition="undecided"
            ),
        )
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", uses=make_ref("b1", "Helper B")
    )
    record_b = make_record("sys_script_include", "b1", _SCOPE, "Helper B")
    captures = (make_capture((record_a, record_b), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include"),)
    )

    result = build_closure(selection, captures, schema_graph)

    items_by_key = {item.key: item for item in result.items}
    assert items_by_key[f"{_SCOPE}|sys_script_include|helper a"].added_by_closure is False
    assert items_by_key[f"{_SCOPE}|sys_script_include|helper b"].added_by_closure is True
    assert len(result.edges) == 1
    assert result.edges[0].dependent_key == f"{_SCOPE}|sys_script_include|helper a"
    assert result.edges[0].dependency_key == f"{_SCOPE}|sys_script_include|helper b"
    assert result.findings == ()


def test_build_closure_stranded_dependency_on_explicit_exclude() -> None:
    selection = _selection(
        (
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper b", disposition="exclude"),
        )
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", uses=make_ref("b1", "Helper B")
    )
    record_b = make_record("sys_script_include", "b1", _SCOPE, "Helper B")
    captures = (make_capture((record_a, record_b), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include"),)
    )

    result = build_closure(selection, captures, schema_graph)

    assert {item.key for item in result.items} == {f"{_SCOPE}|sys_script_include|helper a"}
    assert result.edges == ()
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.kind == FindingKind.STRANDED_DEPENDENCY
    assert finding.subject_key == f"{_SCOPE}|sys_script_include|helper a"
    assert f"{_SCOPE}|sys_script_include|helper b" in finding.detail


def test_build_closure_data_prerequisite_on_stop_list_table() -> None:
    selection = _selection(
        (make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),)
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", assigned_to=make_ref("u1", "Some User")
    )
    captures = (make_capture((record_a,), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "assigned_to", "sys_user"),)
    )

    result = build_closure(selection, captures, schema_graph)

    assert {item.key for item in result.items} == {f"{_SCOPE}|sys_script_include|helper a"}
    assert result.edges == ()
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.kind == FindingKind.DATA_PREREQUISITE
    assert finding.subject_key == f"{_SCOPE}|sys_script_include|helper a"
    assert "sys_user" in finding.detail


def test_build_closure_isolated_item_has_no_edges_or_findings() -> None:
    selection = _selection(
        (make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),)
    )
    record_a = make_record("sys_script_include", "a1", _SCOPE, "Helper A")
    captures = (make_capture((record_a,), instance_id="alectri"),)
    schema_graph = make_schema_graph(())

    result = build_closure(selection, captures, schema_graph)

    assert {item.key for item in result.items} == {f"{_SCOPE}|sys_script_include|helper a"}
    assert result.edges == ()
    assert result.findings == ()


def test_build_closure_seed_item_without_captured_record_stays_in_plan() -> None:
    # A curated "include" item whose capture never produced a matching
    # record (e.g. its scope wasn't found on the source instance) still
    # ends up in the plan -- closure just can't walk its (nonexistent)
    # outbound references.
    selection = _selection(
        (make_selection_item(key=f"{_SCOPE}|sys_script_include|missing", disposition="include"),)
    )
    captures: tuple[CaptureResult, ...] = ()
    schema_graph = make_schema_graph(())

    result = build_closure(selection, captures, schema_graph)

    assert {item.key for item in result.items} == {f"{_SCOPE}|sys_script_include|missing"}
    assert result.edges == ()
    assert result.findings == ()


def test_build_closure_use_case_rollup_key_included_does_not_crash_access_posture_scan() -> None:
    # A USE_CASE rollup key (no "|" separators, e.g. "AI Summit") can reach
    # `items` when a curator marks it disposition="include" even though it
    # aggregates workflows rather than naming a capturable table (its member
    # workflows appear as their own WORKFLOW items). build_closure's AC4
    # access-posture scan must not crash deriving the in-plan table set.
    selection = _selection(
        (
            make_selection_item(key="AI Summit", disposition="include"),
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
        )
    )
    record_a = make_record("sys_script_include", "a1", _SCOPE, "Helper A")
    captures = (make_capture((record_a,), instance_id="alectri"),)
    schema_graph = make_schema_graph(())

    result = build_closure(selection, captures, schema_graph)

    assert {item.key for item in result.items} == {
        "AI Summit",
        f"{_SCOPE}|sys_script_include|helper a",
    }
    assert result.findings == ()


def test_build_closure_reference_edge_with_no_field_value_is_skipped() -> None:
    selection = _selection(
        (make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),)
    )
    record_a = make_record("sys_script_include", "a1", _SCOPE, "Helper A")
    captures = (make_capture((record_a,), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include"),)
    )

    result = build_closure(selection, captures, schema_graph)

    assert result.edges == ()
    assert result.findings == ()


# -- AC2: co-capture rule table ----------------------------------------------


def test_build_closure_acl_role_rows_always_added_regardless_of_disposition() -> None:
    selection = _selection(
        (
            make_selection_item(
                key=f"{_SCOPE}|sys_security_acl|read incident", disposition="include"
            ),
            make_selection_item(
                key=f"{_SCOPE}|sys_security_acl_role|read incident role",
                disposition="exclude",
            ),
        )
    )
    acl = make_record("sys_security_acl", "acl1", _SCOPE, "Read Incident")
    role = make_record(
        "sys_security_acl_role",
        "role1",
        _SCOPE,
        "Read Incident Role",
        sys_security_acl=make_ref("acl1", "Read Incident"),
    )
    captures = (make_capture((acl, role), instance_id="alectri"),)
    schema_graph = make_schema_graph(())

    result = build_closure(selection, captures, schema_graph)

    items_by_key = {item.key: item for item in result.items}
    role_key = f"{_SCOPE}|sys_security_acl_role|read incident role"
    assert role_key in items_by_key
    assert items_by_key[role_key].added_by_closure is True
    # Bypasses disposition: no STRANDED_DEPENDENCY despite the exclude.
    assert result.findings == ()


def test_build_closure_acl_role_rows_bypass_stop_list() -> None:
    selection = _selection(
        (
            make_selection_item(
                key=f"{_SCOPE}|sys_security_acl|read incident", disposition="include"
            ),
        )
    )
    acl = make_record("sys_security_acl", "acl1", _SCOPE, "Read Incident")
    role = make_record(
        "sys_security_acl_role",
        "role1",
        _SCOPE,
        "Read Incident Role",
        sys_security_acl=make_ref("acl1", "Read Incident"),
    )
    captures = (make_capture((acl, role), instance_id="alectri"),)
    schema_graph = make_schema_graph(())

    result = build_closure(selection, captures, schema_graph, stop_list=("sys_security_acl_role",))

    role_key = f"{_SCOPE}|sys_security_acl_role|read incident role"
    assert role_key in {item.key for item in result.items}
    assert result.findings == ()


def test_build_closure_sysauto_script_reference_follows_standard_rule() -> None:
    selection = _selection(
        (
            make_selection_item(
                key=f"{_SCOPE}|sysauto_script|nightly cleanup", disposition="include"
            ),
            make_selection_item(
                key=f"{_SCOPE}|sys_script_include|cleanup helper", disposition="include"
            ),
        )
    )
    job = make_record(
        "sysauto_script", "j1", _SCOPE, "Nightly Cleanup", script=make_ref("s1", "Cleanup Helper")
    )
    script = make_record("sys_script_include", "s1", _SCOPE, "Cleanup Helper")
    captures = (make_capture((job, script), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sysauto_script", "script", "sys_script_include"),)
    )

    result = build_closure(selection, captures, schema_graph)

    assert len(result.edges) == 1
    assert result.edges[0].dependent_key == f"{_SCOPE}|sysauto_script|nightly cleanup"
    assert result.edges[0].dependency_key == f"{_SCOPE}|sys_script_include|cleanup helper"
    assert result.findings == ()


def test_build_closure_flow_snapshot_subflow_action_rows_always_added() -> None:
    selection = _selection(
        (make_selection_item(key=f"{_SCOPE}|sys_hub_flow|approve po", disposition="include"),)
    )
    flow = make_record("sys_hub_flow", "f1", _SCOPE, "Approve PO")
    snapshot = make_record(
        "sys_hub_flow_snapshot", "snap1", _SCOPE, "Approve PO Snapshot", flow=make_ref("f1")
    )
    subflow = make_record(
        "sys_hub_flow_subflow", "sub1", _SCOPE, "Approve PO Subflow", flow=make_ref("f1")
    )
    action = make_record(
        "sys_hub_flow_action_instance", "act1", _SCOPE, "Send Notification", flow=make_ref("f1")
    )
    # Decoy snapshot belonging to a DIFFERENT flow -- must NOT be pulled in
    # by this flow's co-capture rule (linkage mismatch).
    other_flow_snapshot = make_record(
        "sys_hub_flow_snapshot", "snap2", _SCOPE, "Other Flow Snapshot", flow=make_ref("other_flow")
    )
    captures = (
        make_capture((flow, snapshot, subflow, action, other_flow_snapshot), instance_id="alectri"),
    )
    schema_graph = make_schema_graph(())

    result = build_closure(selection, captures, schema_graph)

    items_by_key = {item.key: item for item in result.items}
    for key in (
        f"{_SCOPE}|sys_hub_flow_snapshot|approve po snapshot",
        f"{_SCOPE}|sys_hub_flow_subflow|approve po subflow",
        f"{_SCOPE}|sys_hub_flow_action_instance|send notification",
    ):
        assert key in items_by_key
        assert items_by_key[key].added_by_closure is True
    assert f"{_SCOPE}|sys_hub_flow_snapshot|other flow snapshot" not in items_by_key


# -- AC3: sys_scope_privilege presence check ---------------------------------


def test_build_closure_stranded_dependency_on_missing_scope_privilege_grant() -> None:
    selection = _selection(
        (
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(
                key=f"{_OTHER_SCOPE}|sys_script_include|helper b", disposition="include"
            ),
        )
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", uses=make_ref("b1", "Helper B")
    )
    record_b = make_record("sys_script_include", "b1", _OTHER_SCOPE, "Helper B")
    # Decoy grants that do NOT match (grantee mismatch, then target mismatch)
    # so the presence check must exhaust every row before concluding absent.
    decoy_grantee = make_record(
        "sys_scope_privilege",
        "g0",
        _SCOPE,
        "decoy grantee",
        application="ghost",
        target=_OTHER_SCOPE,
    )
    decoy_target = make_record(
        "sys_scope_privilege", "g1", _SCOPE, "decoy target", application=_SCOPE, target="ghost"
    )
    captures = (
        make_capture((record_a, record_b, decoy_grantee, decoy_target), instance_id="alectri"),
    )
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include", cross_scope=True),)
    )

    result = build_closure(selection, captures, schema_graph)

    stranded = [f for f in result.findings if f.kind == FindingKind.STRANDED_DEPENDENCY]
    assert len(stranded) == 1
    assert stranded[0].subject_key == f"{_SCOPE}|sys_script_include|helper a"
    assert _SCOPE in stranded[0].detail
    assert _OTHER_SCOPE in stranded[0].detail


def test_build_closure_no_finding_when_scope_privilege_grant_present() -> None:
    selection = _selection(
        (
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(
                key=f"{_OTHER_SCOPE}|sys_script_include|helper b", disposition="include"
            ),
        )
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", uses=make_ref("b1", "Helper B")
    )
    record_b = make_record("sys_script_include", "b1", _OTHER_SCOPE, "Helper B")
    grant = make_record(
        "sys_scope_privilege", "g1", _SCOPE, "grant", application=_SCOPE, target=_OTHER_SCOPE
    )
    captures = (make_capture((record_a, record_b, grant), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include", cross_scope=True),)
    )

    result = build_closure(selection, captures, schema_graph)

    assert not any(f.kind == FindingKind.STRANDED_DEPENDENCY for f in result.findings)


# -- AC4: sys_db_object access-posture diff ----------------------------------


def test_build_closure_access_posture_drift_on_differing_fields() -> None:
    selection = _selection(
        (make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),)
    )
    record_a = make_record("sys_script_include", "a1", _SCOPE, "Helper A")
    old_db_object = make_record(
        "sys_db_object",
        "d1",
        _SCOPE,
        "sys_script_include",
        accessible_from="public",
        caller_access="none",
    )
    new_db_object = make_record(
        "sys_db_object",
        "d2",
        _SCOPE,
        "sys_script_include",
        accessible_from="package_private",
        caller_access="none",
    )
    captures = (
        make_capture((record_a, old_db_object), instance_id="alectri"),
        make_capture((new_db_object,), instance_id="retail"),
    )
    schema_graph = make_schema_graph(())

    result = build_closure(selection, captures, schema_graph)

    drift = [f for f in result.findings if f.kind == FindingKind.ACCESS_POSTURE_DRIFT]
    assert len(drift) == 1
    assert drift[0].subject_key == "sys_script_include"
    assert "public" in drift[0].detail
    assert "package_private" in drift[0].detail


def test_build_closure_no_access_posture_drift_when_fields_match() -> None:
    selection = _selection(
        (make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),)
    )
    record_a = make_record("sys_script_include", "a1", _SCOPE, "Helper A")
    old_db_object = make_record(
        "sys_db_object",
        "d1",
        _SCOPE,
        "sys_script_include",
        accessible_from="public",
        caller_access="none",
    )
    new_db_object = make_record(
        "sys_db_object",
        "d2",
        _SCOPE,
        "sys_script_include",
        accessible_from="public",
        caller_access="none",
    )
    captures = (
        make_capture((record_a, old_db_object), instance_id="alectri"),
        make_capture((new_db_object,), instance_id="retail"),
    )
    schema_graph = make_schema_graph(())

    result = build_closure(selection, captures, schema_graph)

    assert not any(f.kind == FindingKind.ACCESS_POSTURE_DRIFT for f in result.findings)


# -- AC5: configurable stop-list ---------------------------------------------


def test_load_stop_list_reads_flat_yaml_list(tmp_path: Path) -> None:
    path = tmp_path / "stop-list.yaml"
    path.write_text(
        "# comment header\n- sys_user\n- sys_user_group\n- sys_choice\n- cmdb_ci\n",
        encoding="utf-8",
    )

    result = load_stop_list(path)

    assert result == ("sys_user", "sys_user_group", "sys_choice", "cmdb_ci")


def test_load_stop_list_malformed_yaml_raises_value_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("key: [unclosed", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid YAML"):
        load_stop_list(path)


def test_load_stop_list_non_list_shape_raises_value_error(tmp_path: Path) -> None:
    path = tmp_path / "not-a-list.yaml"
    path.write_text("key: value\n", encoding="utf-8")

    with pytest.raises(ValueError, match="flat list"):
        load_stop_list(path)


def test_build_closure_custom_stop_list_dampens_like_default(tmp_path: Path) -> None:
    path = tmp_path / "stop-list.yaml"
    path.write_text("- sys_approval\n", encoding="utf-8")
    custom_stop_list = load_stop_list(path)

    selection = _selection(
        (make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),)
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", approval=make_ref("appr1")
    )
    captures = (make_capture((record_a,), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "approval", "sys_approval"),)
    )

    result = build_closure(selection, captures, schema_graph, stop_list=custom_stop_list)

    assert len(result.findings) == 1
    assert result.findings[0].kind == FindingKind.DATA_PREREQUISITE
    assert "sys_approval" in result.findings[0].detail


# -- Cross-cutting: transitive closure, precedence, determinism -------------


def test_build_closure_transitive_undecided_auto_add() -> None:
    selection = _selection(
        (
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(
                key=f"{_SCOPE}|sys_script_include|helper b", disposition="undecided"
            ),
            make_selection_item(
                key=f"{_SCOPE}|sys_script_include|helper c", disposition="undecided"
            ),
        )
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", uses=make_ref("b1", "Helper B")
    )
    record_b = make_record(
        "sys_script_include", "b1", _SCOPE, "Helper B", uses=make_ref("c1", "Helper C")
    )
    record_c = make_record("sys_script_include", "c1", _SCOPE, "Helper C")
    captures = (make_capture((record_a, record_b, record_c), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include"),)
    )

    result = build_closure(selection, captures, schema_graph)

    items_by_key = {item.key: item for item in result.items}
    assert items_by_key[f"{_SCOPE}|sys_script_include|helper b"].added_by_closure is True
    assert items_by_key[f"{_SCOPE}|sys_script_include|helper c"].added_by_closure is True
    assert len(result.edges) == 2


def test_build_closure_mutual_undecided_references_terminate_and_add_once() -> None:
    # Cycle-safety regression guard: A(include) -> B(undecided) -> C(undecided)
    # -> B is a real mutual reference between undecided items resolved through
    # build_closure itself. The walk must terminate, add each undecided item
    # exactly once (the enqueue is guarded by "not in items"), record every
    # ordering edge including the cycle-closing one, and stay deterministic.
    selection = _selection(
        (
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(
                key=f"{_SCOPE}|sys_script_include|helper b", disposition="undecided"
            ),
            make_selection_item(
                key=f"{_SCOPE}|sys_script_include|helper c", disposition="undecided"
            ),
        )
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", uses=make_ref("b1", "Helper B")
    )
    record_b = make_record(
        "sys_script_include", "b1", _SCOPE, "Helper B", uses=make_ref("c1", "Helper C")
    )
    record_c = make_record(
        "sys_script_include", "c1", _SCOPE, "Helper C", uses=make_ref("b1", "Helper B")
    )
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include"),)
    )

    result = build_closure(
        selection,
        (make_capture((record_a, record_b, record_c), instance_id="alectri"),),
        schema_graph,
    )
    shuffled = build_closure(
        selection,
        (make_capture((record_c, record_b, record_a), instance_id="alectri"),),
        schema_graph,
    )

    key_a = f"{_SCOPE}|sys_script_include|helper a"
    key_b = f"{_SCOPE}|sys_script_include|helper b"
    key_c = f"{_SCOPE}|sys_script_include|helper c"
    # Each item appears exactly once (no duplicate adds from the cycle).
    assert [item.key for item in result.items] == [key_a, key_b, key_c]
    items_by_key = {item.key: item for item in result.items}
    assert items_by_key[key_b].added_by_closure is True
    assert items_by_key[key_c].added_by_closure is True
    # All three ordering edges recorded, including the cycle-closing C -> B.
    assert {(e.dependent_key, e.dependency_key) for e in result.edges} == {
        (key_a, key_b),
        (key_b, key_c),
        (key_c, key_b),
    }
    assert result.findings == ()
    assert result == shuffled


def test_build_closure_stop_list_precedes_explicit_exclude() -> None:
    # AC1 row 4 says "any item": a reference target whose table is
    # stop-listed dampens to DATA_PREREQUISITE even when the target's own
    # SelectionItem disposition is an explicit exclude -- the stop-list check
    # takes precedence, so no STRANDED_DEPENDENCY is raised and the row is
    # never added.
    selection = _selection(
        (
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(key=f"{_SCOPE}|cmdb_ci|some ci", disposition="exclude"),
        )
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", ci=make_ref("ci1", "Some CI")
    )
    ci_record = make_record("cmdb_ci", "ci1", _SCOPE, "Some CI")
    captures = (make_capture((record_a, ci_record), instance_id="alectri"),)
    schema_graph = make_schema_graph((make_reference_edge("sys_script_include", "ci", "cmdb_ci"),))

    result = build_closure(selection, captures, schema_graph)

    assert f"{_SCOPE}|cmdb_ci|some ci" not in {item.key for item in result.items}
    assert len(result.findings) == 1
    assert result.findings[0].kind == FindingKind.DATA_PREREQUISITE
    assert "cmdb_ci" in result.findings[0].detail
    assert not any(f.kind == FindingKind.STRANDED_DEPENDENCY for f in result.findings)


def test_build_closure_stop_list_dampens_even_when_target_independently_included() -> None:
    selection = _selection(
        (
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(key=f"{_SCOPE}|cmdb_ci|some ci", disposition="include"),
        )
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", ci=make_ref("ci1", "Some CI")
    )
    ci_record = make_record("cmdb_ci", "ci1", _SCOPE, "Some CI")
    captures = (make_capture((record_a, ci_record), instance_id="alectri"),)
    schema_graph = make_schema_graph((make_reference_edge("sys_script_include", "ci", "cmdb_ci"),))

    result = build_closure(selection, captures, schema_graph)

    # The CI is present because it was independently seeded (explicit
    # include), not because the reference edge added it -- the edge itself
    # is dampened regardless of the target's own disposition.
    assert f"{_SCOPE}|cmdb_ci|some ci" in {item.key for item in result.items}
    assert result.edges == ()
    assert len(result.findings) == 1
    assert result.findings[0].kind == FindingKind.DATA_PREREQUISITE


def test_build_closure_reference_to_uncurated_record_is_noop() -> None:
    selection = _selection(
        (make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),)
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", uses=make_ref("b1", "Helper B")
    )
    record_b = make_record("sys_script_include", "b1", _SCOPE, "Helper B")  # not in Selection
    captures = (make_capture((record_a, record_b), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include"),)
    )

    result = build_closure(selection, captures, schema_graph)

    assert {item.key for item in result.items} == {f"{_SCOPE}|sys_script_include|helper a"}
    assert result.edges == ()
    assert result.findings == ()


def test_build_closure_unresolvable_sys_id_is_noop() -> None:
    selection = _selection(
        (make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),)
    )
    record_a = make_record(
        "sys_script_include", "a1", _SCOPE, "Helper A", uses=make_ref("ghost1", "Ghost")
    )
    captures = (make_capture((record_a,), instance_id="alectri"),)
    schema_graph = make_schema_graph(
        (make_reference_edge("sys_script_include", "uses", "sys_script_include"),)
    )

    result = build_closure(selection, captures, schema_graph)

    assert {item.key for item in result.items} == {f"{_SCOPE}|sys_script_include|helper a"}
    assert result.edges == ()
    assert result.findings == ()


def test_build_closure_is_order_independent() -> None:
    selection = _selection(
        (
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper a", disposition="include"),
            make_selection_item(
                key=f"{_SCOPE}|sys_script_include|helper b", disposition="undecided"
            ),
            make_selection_item(key=f"{_SCOPE}|sys_script_include|helper c", disposition="exclude"),
        )
    )
    record_a = make_record(
        "sys_script_include",
        "a1",
        _SCOPE,
        "Helper A",
        uses=make_ref("b1", "Helper B"),
        also_uses=make_ref("c1", "Helper C"),
    )
    record_b = make_record("sys_script_include", "b1", _SCOPE, "Helper B")
    record_c = make_record("sys_script_include", "c1", _SCOPE, "Helper C")
    schema_graph = make_schema_graph(
        (
            make_reference_edge("sys_script_include", "uses", "sys_script_include"),
            make_reference_edge("sys_script_include", "also_uses", "sys_script_include"),
        )
    )

    forward = build_closure(
        selection,
        (make_capture((record_a, record_b, record_c), instance_id="alectri"),),
        schema_graph,
    )
    shuffled = build_closure(
        selection,
        (make_capture((record_c, record_a, record_b), instance_id="alectri"),),
        schema_graph,
    )

    assert forward == shuffled
