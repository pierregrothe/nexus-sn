# tests/test_migrate_planner.py
# Tests for nexus.migrate.planner (story 04b): AC6-AC10.
# Author: Pierre Grothe
# Date: 2026-07-02

"""AC6-AC10: wave-ordering topology, cycle handling, and approval blocking.

No mocks; ClosureItem/OrderingEdge fixtures are constructed directly (they
carry no ServiceNow-specific data), and MigrationPlan/IntegrityFinding
fixtures come from tests/fakes/migrate.py.
"""

from nexus.migrate.closure import ClosureItem, OrderingEdge
from nexus.migrate.models import FindingKind
from nexus.migrate.planner import build_waves, detect_cycles, validate_approval
from tests.fakes.migrate import (
    make_acknowledgment,
    make_integrity_finding,
    make_migration_plan,
    make_waiver,
)

# -- AC6: topological wave ordering ------------------------------------------


def test_build_waves_topologically_valid_and_shares_earliest_wave() -> None:
    items = tuple(ClosureItem(key=key) for key in ("A", "B", "C", "D", "E"))
    edges = (
        OrderingEdge(dependent_key="C", dependency_key="A"),
        OrderingEdge(dependent_key="D", dependency_key="B"),
        OrderingEdge(dependent_key="E", dependency_key="C"),
        OrderingEdge(dependent_key="E", dependency_key="D"),
    )

    waves = build_waves(items, edges)

    wave_index = {item.key: wave.index for wave in waves for item in wave.items}
    assert wave_index["A"] == 0
    assert wave_index["B"] == 0
    assert wave_index["C"] == 1
    assert wave_index["D"] == 1
    assert wave_index["E"] == 2
    for edge in edges:
        assert wave_index[edge.dependent_key] > wave_index[edge.dependency_key]
    # Wave 0 holds both unconstrained items, sorted lexicographically by key.
    assert [item.key for item in waves[0].items] == ["A", "B"]


def test_build_waves_ignores_edges_referencing_unknown_items() -> None:
    items = (ClosureItem(key="A"),)
    edges = (OrderingEdge(dependent_key="A", dependency_key="ghost"),)

    waves = build_waves(items, edges)

    assert len(waves) == 1
    assert waves[0].index == 0
    assert waves[0].items[0].key == "A"


def test_build_waves_is_order_independent() -> None:
    items = tuple(ClosureItem(key=key) for key in ("A", "B", "C", "D", "E"))
    edges = (
        OrderingEdge(dependent_key="C", dependency_key="A"),
        OrderingEdge(dependent_key="D", dependency_key="B"),
        OrderingEdge(dependent_key="E", dependency_key="C"),
        OrderingEdge(dependent_key="E", dependency_key="D"),
    )

    forward = build_waves(items, edges)
    shuffled = build_waves(tuple(reversed(items)), tuple(reversed(edges)))

    assert forward == shuffled


# -- AC7: cycle handling ------------------------------------------------------


def test_build_waves_places_cycle_members_in_single_wave() -> None:
    items = tuple(ClosureItem(key=key) for key in ("A", "B", "C"))
    edges = (
        OrderingEdge(dependent_key="A", dependency_key="B"),
        OrderingEdge(dependent_key="B", dependency_key="C"),
        OrderingEdge(dependent_key="C", dependency_key="A"),
    )

    waves = build_waves(items, edges)

    assert len(waves) == 1
    assert {item.key for item in waves[0].items} == {"A", "B", "C"}


def test_detect_cycles_names_all_cycle_members_sorted() -> None:
    items = tuple(ClosureItem(key=key) for key in ("A", "B", "C"))
    edges = (
        OrderingEdge(dependent_key="A", dependency_key="B"),
        OrderingEdge(dependent_key="B", dependency_key="C"),
        OrderingEdge(dependent_key="C", dependency_key="A"),
    )

    findings = detect_cycles(items, edges)

    assert len(findings) == 1
    assert findings[0].kind == FindingKind.CYCLE
    assert findings[0].subject_key == "A"
    assert "A" in findings[0].detail
    assert "B" in findings[0].detail
    assert "C" in findings[0].detail


def test_build_waves_positions_cycle_after_noncycle_dependency() -> None:
    items = tuple(ClosureItem(key=key) for key in ("A", "B", "C", "D"))
    edges = (
        OrderingEdge(dependent_key="A", dependency_key="B"),
        OrderingEdge(dependent_key="B", dependency_key="C"),
        OrderingEdge(dependent_key="C", dependency_key="A"),
        OrderingEdge(dependent_key="A", dependency_key="D"),
    )

    waves = build_waves(items, edges)

    wave_index = {item.key: wave.index for wave in waves for item in wave.items}
    assert wave_index["D"] == 0
    assert wave_index["A"] == wave_index["B"] == wave_index["C"] == 1


def test_build_waves_treats_self_loop_as_single_item_cycle() -> None:
    items = (ClosureItem(key="A"),)
    edges = (OrderingEdge(dependent_key="A", dependency_key="A"),)

    waves = build_waves(items, edges)
    findings = detect_cycles(items, edges)

    assert len(waves) == 1
    assert waves[0].items[0].key == "A"
    assert len(findings) == 1
    assert findings[0].kind == FindingKind.CYCLE
    assert findings[0].subject_key == "A"


# -- AC8/AC9: STRANDED_DEPENDENCY blocking -----------------------------------


def test_validate_approval_unwaived_stranded_dependency_blocks() -> None:
    finding = make_integrity_finding(kind=FindingKind.STRANDED_DEPENDENCY, waiver=None)
    plan = make_migration_plan(findings=(finding,))

    reasons = validate_approval(plan)

    assert len(reasons) == 1
    assert "STRANDED_DEPENDENCY" in reasons[0]
    assert finding.subject_key in reasons[0]


def test_validate_approval_waived_stranded_dependency_does_not_block() -> None:
    finding = make_integrity_finding(kind=FindingKind.STRANDED_DEPENDENCY, waiver=make_waiver())
    plan = make_migration_plan(findings=(finding,))

    reasons = validate_approval(plan)

    assert reasons == ()


# -- AC10: DATA_PREREQUISITE blocking ----------------------------------------


def test_validate_approval_unacknowledged_data_prerequisite_blocks() -> None:
    finding = make_integrity_finding(kind=FindingKind.DATA_PREREQUISITE, acknowledgment=None)
    plan = make_migration_plan(findings=(finding,))

    reasons = validate_approval(plan)

    assert len(reasons) == 1
    assert "DATA_PREREQUISITE" in reasons[0]
    assert finding.subject_key in reasons[0]


def test_validate_approval_acknowledged_data_prerequisite_does_not_block() -> None:
    finding = make_integrity_finding(
        kind=FindingKind.DATA_PREREQUISITE, acknowledgment=make_acknowledgment()
    )
    plan = make_migration_plan(findings=(finding,))

    reasons = validate_approval(plan)

    assert reasons == ()


# -- CYCLE / ACCESS_POSTURE_DRIFT: documented non-blocking behavior ---------


def test_validate_approval_cycle_and_drift_findings_never_block() -> None:
    cycle_finding = make_integrity_finding(
        kind=FindingKind.CYCLE,
        subject_key="a",
        detail="dependency cycle among: a, b",
    )
    drift_finding = make_integrity_finding(
        kind=FindingKind.ACCESS_POSTURE_DRIFT,
        subject_key="sys_script_include",
        detail="access posture drifted",
    )
    plan = make_migration_plan(findings=(cycle_finding, drift_finding))

    reasons = validate_approval(plan)

    assert reasons == ()


# -- Finding 3 (fix wave 2): KEY_COLLISION never blocks ----------------------


def test_validate_approval_key_collision_finding_never_blocks() -> None:
    collision_finding = make_integrity_finding(
        kind=FindingKind.KEY_COLLISION,
        subject_key="x_alectri_core|sys_hub_flow|dup",
        detail="natural key collides across sys_ids: a1, z9 -- kept 'a1'",
    )
    plan = make_migration_plan(findings=(collision_finding,))

    reasons = validate_approval(plan)

    assert reasons == ()
