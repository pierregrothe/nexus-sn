# tests/test_plugins_drift.py
# Tests for single-instance over-time plugin drift detection.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for PluginDriftEntry / PluginDriftReport / compute_drift."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.plugins.drift import (
    PluginDriftEntry,
    PluginDriftReport,
    compute_drift,
)
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _entry(**overrides: object) -> PluginDriftEntry:
    defaults: dict[str, object] = {
        "plugin_id": "com.snc.incident",
        "name": "Incident Management",
        "product_family": "ITSM",
        "status": "version_changed",
        "baseline_version": "1.0.0",
        "current_version": "1.2.0",
        "baseline_state": "active",
        "current_state": "active",
    }
    defaults.update(overrides)
    return PluginDriftEntry.model_validate(defaults)


def _info(
    plugin_id: str,
    *,
    version: str = "1.0.0",
    state: str = "active",
    product_family: str = "ITSM",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": version,
            "state": state,
            "source": "servicenow",
            "product_family": product_family,
            "depends_on": (),
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        plugins=plugins,
    )


def test_plugin_drift_entry_construction_with_required_fields() -> None:
    entry = _entry()
    assert entry.plugin_id == "com.snc.incident"
    assert entry.status == "version_changed"


def test_plugin_drift_entry_is_frozen() -> None:
    entry = _entry()
    with pytest.raises(ValidationError):
        entry.plugin_id = "renamed"


def test_plugin_drift_entry_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        _entry(status="weird")


def test_plugin_drift_entry_accepts_none_for_baseline_fields_when_added() -> None:
    entry = _entry(status="added", baseline_version=None, baseline_state=None)
    assert entry.baseline_version is None
    assert entry.baseline_state is None


def test_plugin_drift_report_holds_profile_and_captured_at_pair() -> None:
    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    t1 = datetime(2026, 5, 12, tzinfo=UTC)
    report = PluginDriftReport(
        profile="prod",
        baseline_captured_at=t0,
        current_captured_at=t1,
        entries=(_entry(),),
    )
    assert report.profile == "prod"
    assert report.baseline_captured_at == t0
    assert report.current_captured_at == t1


def test_compute_drift_returns_empty_when_inventories_identical() -> None:
    inv = _inventory(_info("com.snc.incident"))
    report = compute_drift(inv, inv, "prod")
    assert report.entries == ()


def test_compute_drift_emits_added_for_plugin_only_in_current() -> None:
    baseline = _inventory()
    current = _inventory(_info("com.snc.new"))
    report = compute_drift(baseline, current, "prod")
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.plugin_id == "com.snc.new"
    assert entry.status == "added"
    assert entry.baseline_version is None
    assert entry.baseline_state is None
    assert entry.current_version == "1.0.0"
    assert entry.current_state == "active"


def test_compute_drift_emits_removed_for_plugin_only_in_baseline() -> None:
    baseline = _inventory(_info("com.snc.gone"))
    current = _inventory()
    report = compute_drift(baseline, current, "prod")
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.plugin_id == "com.snc.gone"
    assert entry.status == "removed"
    assert entry.baseline_version == "1.0.0"
    assert entry.current_version is None


def test_compute_drift_emits_version_changed_when_versions_differ() -> None:
    baseline = _inventory(_info("com.snc.x", version="1.0.0"))
    current = _inventory(_info("com.snc.x", version="2.0.0"))
    report = compute_drift(baseline, current, "prod")
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.status == "version_changed"
    assert entry.baseline_version == "1.0.0"
    assert entry.current_version == "2.0.0"


def test_compute_drift_emits_state_changed_when_state_flipped() -> None:
    baseline = _inventory(_info("com.snc.x", state="inactive"))
    current = _inventory(_info("com.snc.x", state="active"))
    report = compute_drift(baseline, current, "prod")
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.status == "state_changed"
    assert entry.baseline_state == "inactive"
    assert entry.current_state == "active"


def test_compute_drift_uses_version_changed_when_both_version_and_state_differ() -> None:
    """version_changed wins as the primary key; both fields populated."""
    baseline = _inventory(_info("com.snc.x", version="1.0.0", state="inactive"))
    current = _inventory(_info("com.snc.x", version="2.0.0", state="active"))
    report = compute_drift(baseline, current, "prod")
    assert len(report.entries) == 1
    entry = report.entries[0]
    assert entry.status == "version_changed"
    assert entry.baseline_version == "1.0.0"
    assert entry.current_version == "2.0.0"
    assert entry.baseline_state == "inactive"
    assert entry.current_state == "active"


def test_compute_drift_sorts_entries_by_product_family_then_plugin_id() -> None:
    baseline = _inventory()
    current = _inventory(
        _info("com.b.alpha", product_family="ITSM"),
        _info("com.a.alpha", product_family="HRSD"),
        _info("com.a.beta", product_family="HRSD"),
    )
    report = compute_drift(baseline, current, "prod")
    ids = [e.plugin_id for e in report.entries]
    assert ids == ["com.a.alpha", "com.a.beta", "com.b.alpha"]


def test_compute_drift_returns_mixed_statuses() -> None:
    baseline = _inventory(
        _info("com.a", version="1.0.0"),
        _info("com.gone"),
        _info("com.flip", state="inactive"),
    )
    current = _inventory(
        _info("com.a", version="2.0.0"),
        _info("com.new"),
        _info("com.flip", state="active"),
    )
    report = compute_drift(baseline, current, "prod")
    statuses = sorted(e.status for e in report.entries)
    assert statuses == ["added", "removed", "state_changed", "version_changed"]


def test_compute_drift_records_captured_at_from_both_inventories() -> None:
    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    t1 = datetime(2026, 5, 12, tzinfo=UTC)
    baseline = PluginInventory(captured_at=t0, sn_version="Xanadu", plugins=())
    current = PluginInventory(captured_at=t1, sn_version="Xanadu", plugins=())
    report = compute_drift(baseline, current, "prod")
    assert report.baseline_captured_at == t0
    assert report.current_captured_at == t1
