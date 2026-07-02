# tests/test_migrate_recheck.py
# Tests for nexus.migrate.recheck (story 06b): compute_drift, AC1-AC4.
# Author: Pierre Grothe
# Date: 2026-07-02

"""Pure tests for the plan --recheck drift-detection core.

No mocks; every MigrationPlan/BaselineEntry fixture comes from
tests/fakes/migrate.py or is built directly (frozen Pydantic models).
"""

from nexus.migrate.models import BaselineEntry
from nexus.migrate.recheck import compute_drift, listing_from_entries, plan_has_baseline
from tests.fakes.migrate import make_baseline_entry, make_migration_plan

_KEY_A = "x_acme_app|sys_script_include|helper a"
_KEY_B = "x_acme_app|sys_script_include|helper b"
_KEY_C = "x_acme_app|sys_script_include|helper c"
_FP1 = "2026-07-01 10:00:00"
_FP2 = "2026-07-02 10:00:00"


# -- listing_from_entries -------------------------------------------------


def test_listing_from_entries_builds_key_to_fingerprint_mapping() -> None:
    entries = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    assert listing_from_entries(entries) == {_KEY_A: (_FP1,)}


def test_listing_from_entries_empty_entries_returns_empty_mapping() -> None:
    assert listing_from_entries(()) == {}


def test_listing_from_entries_duplicate_key_collects_multiset_sorted() -> None:
    entries = (
        BaselineEntry(key=_KEY_A, fingerprint=_FP2),
        BaselineEntry(key=_KEY_A, fingerprint=_FP1),
    )
    assert listing_from_entries(entries) == {_KEY_A: (_FP1, _FP2)}


# -- plan_has_baseline (empty-baseline detection) --------------------------


def test_plan_has_baseline_true_when_source_baseline_populated() -> None:
    plan = make_migration_plan(source_baseline=(make_baseline_entry(),), target_baseline=())
    assert plan_has_baseline(plan) is True


def test_plan_has_baseline_true_when_target_baseline_populated() -> None:
    plan = make_migration_plan(source_baseline=(), target_baseline=(make_baseline_entry(),))
    assert plan_has_baseline(plan) is True


def test_plan_has_baseline_false_when_both_baselines_empty() -> None:
    plan = make_migration_plan(source_baseline=(), target_baseline=())
    assert plan_has_baseline(plan) is False


# -- compute_drift: no drift (AC1) -----------------------------------------


def test_compute_drift_reports_no_drift_when_listings_match_baseline() -> None:
    baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan = make_migration_plan(source_baseline=baseline, target_baseline=baseline)
    listing = listing_from_entries(baseline)

    report = compute_drift(plan, listing, listing)

    assert report.has_drift is False
    assert report.source_added == ()
    assert report.source_removed == ()
    assert report.source_changed == ()
    assert report.target_added == ()
    assert report.target_removed == ()
    assert report.target_changed == ()


# -- compute_drift: added (AC2) ---------------------------------------------


def test_compute_drift_reports_source_added_artifact() -> None:
    baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan = make_migration_plan(source_baseline=baseline, target_baseline=())
    fresh_source = listing_from_entries(
        (
            make_baseline_entry(key=_KEY_A, fingerprint=_FP1),
            make_baseline_entry(key=_KEY_B, fingerprint=_FP1),
        )
    )

    report = compute_drift(plan, fresh_source, {})

    assert report.source_added == (_KEY_B,)
    assert report.source_removed == ()
    assert report.source_changed == ()
    assert report.has_drift is True


def test_compute_drift_reports_target_added_artifact() -> None:
    plan = make_migration_plan(source_baseline=(), target_baseline=())
    fresh_target = listing_from_entries((make_baseline_entry(key=_KEY_A, fingerprint=_FP1),))

    report = compute_drift(plan, {}, fresh_target)

    assert report.target_added == (_KEY_A,)
    assert report.has_drift is True


# -- compute_drift: removed (AC2) --------------------------------------------


def test_compute_drift_reports_source_removed_artifact() -> None:
    baseline = (
        make_baseline_entry(key=_KEY_A, fingerprint=_FP1),
        make_baseline_entry(key=_KEY_B, fingerprint=_FP1),
    )
    plan = make_migration_plan(source_baseline=baseline, target_baseline=())
    fresh_source = listing_from_entries((make_baseline_entry(key=_KEY_A, fingerprint=_FP1),))

    report = compute_drift(plan, fresh_source, {})

    assert report.source_removed == (_KEY_B,)
    assert report.source_added == ()
    assert report.has_drift is True


def test_compute_drift_reports_target_removed_artifact() -> None:
    baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan = make_migration_plan(source_baseline=(), target_baseline=baseline)

    report = compute_drift(plan, {}, {})

    assert report.target_removed == (_KEY_A,)
    assert report.has_drift is True


# -- compute_drift: changed (AC4) --------------------------------------------


def test_compute_drift_reports_changed_artifact_distinct_from_added_removed() -> None:
    baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan = make_migration_plan(source_baseline=baseline, target_baseline=())
    fresh_source = listing_from_entries((make_baseline_entry(key=_KEY_A, fingerprint=_FP2),))

    report = compute_drift(plan, fresh_source, {})

    assert report.source_changed == (_KEY_A,)
    assert report.source_added == ()
    assert report.source_removed == ()
    assert report.has_drift is True


def test_compute_drift_same_fingerprint_is_not_changed() -> None:
    baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan = make_migration_plan(source_baseline=baseline, target_baseline=())
    fresh_source = listing_from_entries((make_baseline_entry(key=_KEY_A, fingerprint=_FP1),))

    report = compute_drift(plan, fresh_source, {})

    assert report.source_changed == ()
    assert report.has_drift is False


# -- compute_drift: multiset fingerprints (AC4, duplicate keys) -------------


def test_compute_drift_multiset_one_of_two_duplicate_keys_changed_reports_once() -> None:
    baseline = (
        make_baseline_entry(key=_KEY_A, fingerprint=_FP1),
        make_baseline_entry(key=_KEY_A, fingerprint=_FP2),
    )
    plan = make_migration_plan(source_baseline=baseline, target_baseline=())
    # One of the two same-key artifacts changed fingerprint (FP1 -> a new
    # value); the other (FP2) is unchanged. Reported as "changed" ONCE for
    # the shared key, not twice.
    fresh_source = listing_from_entries(
        (
            BaselineEntry(key=_KEY_A, fingerprint="2026-07-03 10:00:00"),
            BaselineEntry(key=_KEY_A, fingerprint=_FP2),
        )
    )

    report = compute_drift(plan, fresh_source, {})

    assert report.source_changed == (_KEY_A,)
    assert len(report.source_changed) == 1


def test_compute_drift_multiset_identical_fingerprints_regardless_of_order_no_drift() -> None:
    baseline = (
        make_baseline_entry(key=_KEY_A, fingerprint=_FP2),
        make_baseline_entry(key=_KEY_A, fingerprint=_FP1),
    )
    plan = make_migration_plan(source_baseline=baseline, target_baseline=())
    fresh_source = listing_from_entries(
        (
            make_baseline_entry(key=_KEY_A, fingerprint=_FP1),
            make_baseline_entry(key=_KEY_A, fingerprint=_FP2),
        )
    )

    report = compute_drift(plan, fresh_source, {})

    assert report.source_changed == ()
    assert report.has_drift is False


# -- compute_drift: determinism (sorted, input-order independent) -----------


def test_compute_drift_source_added_is_sorted_regardless_of_input_order() -> None:
    plan = make_migration_plan(source_baseline=(), target_baseline=())
    fresh_source = listing_from_entries(
        (
            make_baseline_entry(key=_KEY_C, fingerprint=_FP1),
            make_baseline_entry(key=_KEY_A, fingerprint=_FP1),
            make_baseline_entry(key=_KEY_B, fingerprint=_FP1),
        )
    )

    report = compute_drift(plan, fresh_source, {})

    assert report.source_added == (_KEY_A, _KEY_B, _KEY_C)


def test_compute_drift_deterministic_across_repeated_calls() -> None:
    baseline = (make_baseline_entry(key=_KEY_A, fingerprint=_FP1),)
    plan = make_migration_plan(source_baseline=baseline, target_baseline=baseline)
    fresh = listing_from_entries(
        (
            make_baseline_entry(key=_KEY_B, fingerprint=_FP1),
            make_baseline_entry(key=_KEY_C, fingerprint=_FP1),
        )
    )

    first = compute_drift(plan, fresh, fresh)
    second = compute_drift(plan, fresh, fresh)

    assert first == second
