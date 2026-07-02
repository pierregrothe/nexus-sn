# src/nexus/migrate/recheck.py
# Pure drift detection: MigrationPlan baselines vs. a fresh re-inventory.
# Author: Pierre Grothe
# Date: 2026-07-02

"""`plan --recheck` drift detection core (Story 06).

``compute_drift`` diffs a ``MigrationPlan``'s recorded ``source_baseline``/
``target_baseline`` against a fresh instance-wide re-inventory of both
instances, reporting added/removed/changed artifacts per instance (AC1-AC4,
ADR-026 Decision 4: freshness is enforced, not assumed). Pure -- no I/O, no
ServiceNow client; the CLI layer (``nexus.cli.commands_migrate``) supplies
both listings via an injectable collaborator seam and never mutates the
plan itself.
"""

from collections.abc import Iterable, Mapping

from nexus.migrate.models import BaselineEntry, DriftReport, MigrationPlan

__all__ = ["compute_drift", "listing_from_entries", "plan_has_baseline"]


def listing_from_entries(entries: Iterable[BaselineEntry]) -> dict[str, tuple[str, ...]]:
    """Build a natural-key -> sorted-fingerprint-multiset mapping from BaselineEntries.

    Duplicate keys are expected (e.g. same-named ``sys_security_acl`` rows
    across operations) and handled as a MULTISET: every fingerprint
    recorded for a key is kept, sorted for order-independent comparison.

    Args:
        entries: BaselineEntry rows -- either a MigrationPlan's baseline or
            a fresh re-inventory listing.

    Returns:
        Mapping of natural key to the sorted tuple of fingerprints recorded
        for that key.
    """
    grouped: dict[str, list[str]] = {}
    for entry in entries:
        grouped.setdefault(entry.key, []).append(entry.fingerprint)
    return {key: tuple(sorted(fingerprints)) for key, fingerprints in grouped.items()}


def plan_has_baseline(plan: MigrationPlan) -> bool:
    """Whether a MigrationPlan carries a usable recheck baseline.

    A plan predating Story 06, or one whose source and target instances both
    happened to be legitimately empty at plan-assembly time, are
    indistinguishable from each other by field values alone -- both leave
    ``source_baseline``/``target_baseline`` empty. This treats "both
    baselines empty" as unusable for recheck (the honest, simple rule): the
    caller should ask the user to regenerate the plan on this version.

    Args:
        plan: The loaded MigrationPlan.

    Returns:
        True when at least one of source_baseline/target_baseline is
        non-empty.
    """
    return bool(plan.source_baseline) or bool(plan.target_baseline)


def _added(
    baseline: Mapping[str, tuple[str, ...]], fresh: Mapping[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """Keys present in ``fresh`` but not ``baseline``, sorted."""
    return tuple(sorted(set(fresh) - set(baseline)))


def _removed(
    baseline: Mapping[str, tuple[str, ...]], fresh: Mapping[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """Keys present in ``baseline`` but not ``fresh``, sorted."""
    return tuple(sorted(set(baseline) - set(fresh)))


def _changed(
    baseline: Mapping[str, tuple[str, ...]], fresh: Mapping[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """Keys present in both with a differing fingerprint multiset, sorted."""
    common = set(baseline) & set(fresh)
    return tuple(sorted(key for key in common if baseline[key] != fresh[key]))


def compute_drift(
    plan: MigrationPlan,
    source_listing: Mapping[str, tuple[str, ...]],
    target_listing: Mapping[str, tuple[str, ...]],
) -> DriftReport:
    """Diff a MigrationPlan's baselines against a fresh re-inventory (AC1-AC4).

    Args:
        plan: The loaded MigrationPlan, carrying source_baseline/target_baseline.
        source_listing: Fresh natural-key -> fingerprint-multiset listing of
            the source instance (``listing_from_entries`` output shape).
        target_listing: Same, for the target instance.

    Returns:
        A DriftReport with added/removed/changed keys per instance, each a
        sorted tuple independent of input order (determinism).
    """
    source_baseline = listing_from_entries(plan.source_baseline)
    target_baseline = listing_from_entries(plan.target_baseline)
    return DriftReport(
        source_added=_added(source_baseline, source_listing),
        source_removed=_removed(source_baseline, source_listing),
        source_changed=_changed(source_baseline, source_listing),
        target_added=_added(target_baseline, target_listing),
        target_removed=_removed(target_baseline, target_listing),
        target_changed=_changed(target_baseline, target_listing),
    )
