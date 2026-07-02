# tests/test_migrate_package.py
# Tests for nexus.migrate's package-level public surface (fix wave 2).
# Author: Pierre Grothe
# Date: 2026-07-02

"""Package-surface tests for nexus.migrate.__init__.

Regression guard (fix wave 2, Finding 2): PreflightStatus/PreflightItemResult/
PreflightReport/run_preflight/MIGRATE_PREFLIGHT_PROBES were defined in
nexus.migrate.models/preflight but never re-exported from nexus.migrate
itself, so `from nexus.migrate import PreflightReport` raised ImportError
even though every sibling story's models were re-exported at the package
level.
"""

import nexus.migrate as migrate_pkg
from nexus.migrate import (
    MIGRATE_PREFLIGHT_PROBES,
    PreflightItemResult,
    PreflightReport,
    PreflightStatus,
    run_preflight,
)

__all__: list[str] = []


def test_migrate_package_exports_preflight_names() -> None:
    assert PreflightStatus is not None
    assert PreflightItemResult is not None
    assert PreflightReport is not None
    assert run_preflight is not None
    assert MIGRATE_PREFLIGHT_PROBES


def test_migrate_package_all_lists_every_public_name() -> None:
    assert set(migrate_pkg.__all__) == {
        "DEFAULT_STOP_LIST",
        "MIGRATE_PREFLIGHT_PROBES",
        "Acknowledgment",
        "BaselineEntry",
        "ClosureItem",
        "ClosureResult",
        "DriftReport",
        "FindingKind",
        "IntegrityFinding",
        "MigrationPlan",
        "OrderingEdge",
        "PlanItem",
        "PlanLane",
        "PreflightItemResult",
        "PreflightReport",
        "PreflightStatus",
        "Selection",
        "SelectionItem",
        "Waiver",
        "Wave",
        "build_capture_for_selection",
        "build_closure",
        "build_waves",
        "compute_drift",
        "detect_cycles",
        "emit_plan_yaml",
        "emit_selection_yaml",
        "field_display",
        "listing_from_entries",
        "load_plan_yaml",
        "load_selection_yaml",
        "load_stop_list",
        "natural_key_segment",
        "plan_has_baseline",
        "record_natural_key",
        "run_preflight",
        "validate_approval",
    }


def test_migrate_package_all_names_are_importable() -> None:
    missing = [name for name in migrate_pkg.__all__ if not hasattr(migrate_pkg, name)]
    assert missing == []
