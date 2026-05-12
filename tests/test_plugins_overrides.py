# tests/test_plugins_overrides.py
# Tests for advisory override models and apply_overrides.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for AdvisoryOverride, AdvisoryOverrideSet, apply_overrides."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import nexus.plugins as plugins_pkg
from nexus.plugins.models import AdvisoryFinding, AdvisorySet, AdvisoryType, Severity
from nexus.plugins.overrides import (
    AdvisoryOverride,
    AdvisoryOverrideSet,
    apply_overrides,
)

__all__: list[str] = []


def _finding(
    plugin_id: str = "com.x",
    advisory_type: AdvisoryType = AdvisoryType.CVE,
    details: str = "CVE-2024-1",
    severity: Severity = Severity.HIGH,
) -> AdvisoryFinding:
    return AdvisoryFinding(
        plugin_id=plugin_id,
        plugin_name=plugin_id,
        plugin_version="1.0",
        advisory_type=advisory_type,
        severity=severity,
        summary="x",
        details=details,
    )


def _override(
    plugin_id: str = "com.x",
    advisory_type: AdvisoryType = AdvisoryType.CVE,
    details: str = "CVE-2024-1",
    reason: str = "ok",
) -> AdvisoryOverride:
    return AdvisoryOverride(
        plugin_id=plugin_id,
        advisory_type=advisory_type,
        details=details,
        reason=reason,
        created_at=datetime(2026, 5, 12, tzinfo=UTC),
    )


def test_advisory_override_is_frozen() -> None:
    o = _override()
    with pytest.raises(ValidationError):
        o.reason = "changed"


def test_advisory_override_rejects_empty_reason() -> None:
    with pytest.raises(ValidationError):
        AdvisoryOverride(
            plugin_id="com.x",
            advisory_type=AdvisoryType.CVE,
            details="CVE-2024-1",
            reason="",
            created_at=datetime(2026, 5, 12, tzinfo=UTC),
        )


def test_advisory_override_set_round_trips_through_json() -> None:
    s = AdvisoryOverrideSet(overrides=(_override(),))
    re = AdvisoryOverrideSet.model_validate_json(s.model_dump_json())
    assert re == s


def test_apply_overrides_with_no_overrides_returns_all_findings() -> None:
    findings = (_finding("com.a"), _finding("com.b"))
    advisories = AdvisorySet(findings=findings)
    overrides = AdvisoryOverrideSet(overrides=())
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == findings
    assert deferred == ()


def test_apply_overrides_filters_matching_finding() -> None:
    finding = _finding("com.x", AdvisoryType.CVE, "CVE-2024-1")
    advisories = AdvisorySet(findings=(finding,))
    overrides = AdvisoryOverrideSet(overrides=(_override("com.x", AdvisoryType.CVE, "CVE-2024-1"),))
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == ()
    assert deferred == (finding,)


def test_apply_overrides_no_match_on_different_details() -> None:
    finding = _finding(details="CVE-2024-1")
    advisories = AdvisorySet(findings=(finding,))
    overrides = AdvisoryOverrideSet(overrides=(_override(details="CVE-2024-2"),))
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == (finding,)
    assert deferred == ()


def test_apply_overrides_no_match_on_different_advisory_type() -> None:
    finding = _finding(advisory_type=AdvisoryType.CVE)
    advisories = AdvisorySet(findings=(finding,))
    overrides = AdvisoryOverrideSet(overrides=(_override(advisory_type=AdvisoryType.EOL),))
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == (finding,)
    assert deferred == ()


def test_apply_overrides_preserves_sort_order_of_remaining() -> None:
    a, b, c = _finding("com.a"), _finding("com.b"), _finding("com.c")
    advisories = AdvisorySet(findings=(a, b, c))
    overrides = AdvisoryOverrideSet(overrides=(_override("com.b"),))
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == (a, c)
    assert deferred == (b,)


def test_apply_overrides_multi_match_filters_all() -> None:
    f1 = _finding("com.x", AdvisoryType.CVE, "CVE-2024-1")
    f2 = _finding("com.x", AdvisoryType.CVE, "CVE-2024-2")
    advisories = AdvisorySet(findings=(f1, f2))
    overrides = AdvisoryOverrideSet(
        overrides=(
            _override("com.x", AdvisoryType.CVE, "CVE-2024-1"),
            _override("com.x", AdvisoryType.CVE, "CVE-2024-2"),
        )
    )
    remaining, deferred = apply_overrides(advisories, overrides)
    assert remaining.findings == ()
    assert len(deferred) == 2
    assert {d.details for d in deferred} == {"CVE-2024-1", "CVE-2024-2"}


def test_public_api_reexports() -> None:
    for name in ("AdvisoryOverride", "AdvisoryOverrideSet", "apply_overrides"):
        assert name in plugins_pkg.__all__
        assert hasattr(plugins_pkg, name)
