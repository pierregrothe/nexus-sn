# tests/test_plugins_models.py
# Tests for the plugins layer Pydantic models.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for PluginInfo, PluginInventory, and ProductFamily."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from nexus.plugins.models import (
    AdvisoryFinding,
    AdvisorySet,
    AdvisoryType,
    PluginInfo,
    PluginInventory,
    ProductFamily,
    Severity,
)

__all__: list[str] = []


def _info(**overrides: object) -> PluginInfo:
    defaults: dict[str, object] = {
        "plugin_id": "com.snc.incident",
        "name": "Incident Management",
        "version": "1.0.0",
        "state": "active",
        "source": "servicenow",
        "product_family": "ITSM",
        "depends_on": (),
        "sys_id": "abc123",
        "installed_at": None,
    }
    defaults.update(overrides)
    return PluginInfo.model_validate(defaults)


def test_product_family_includes_all_curated_families() -> None:
    for name in (
        "ITSM",
        "ITOM",
        "ITAM",
        "SPM",
        "CSM",
        "HRSD",
        "FSM",
        "GRC",
        "IRM",
        "SecOps",
        "Platform",
        "Uncategorized",
    ):
        assert any(f.value == name for f in ProductFamily)


def test_plugin_info_construction_with_required_fields() -> None:
    info = _info()
    assert info.plugin_id == "com.snc.incident"
    assert info.state == "active"


def test_plugin_info_is_frozen() -> None:
    info = _info()
    with pytest.raises(ValidationError):
        info.name = "renamed"


def test_plugin_info_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PluginInfo.model_validate({**_info().model_dump(), "extra": "x"})


def test_plugin_info_rejects_unknown_state() -> None:
    with pytest.raises(ValidationError):
        _info(state="unknown")


def test_plugin_info_rejects_unknown_source() -> None:
    with pytest.raises(ValidationError):
        _info(source="vendor")


def test_plugin_inventory_holds_captured_at_and_plugins() -> None:
    now = datetime.now(UTC)
    inv = PluginInventory(captured_at=now, sn_version="Xanadu", plugins=(_info(),))
    assert inv.captured_at == now
    assert inv.plugins[0].plugin_id == "com.snc.incident"


def test_plugin_inventory_is_frozen() -> None:
    inv = PluginInventory(captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=())
    with pytest.raises(ValidationError):
        inv.sn_version = "Yokohama"


def test_plugin_inventory_round_trips_through_json() -> None:
    inv = PluginInventory(captured_at=datetime.now(UTC), sn_version="Xanadu", plugins=(_info(),))
    re = PluginInventory.model_validate_json(inv.model_dump_json())
    assert re == inv


def test_plugin_info_defaults_latest_version_to_none() -> None:
    info = _info()
    assert info.latest_version is None


def test_plugin_info_accepts_latest_version_field() -> None:
    info = _info(latest_version="2.0.0")
    assert info.latest_version == "2.0.0"


def test_severity_has_four_levels() -> None:
    assert {s.value for s in Severity} == {"critical", "high", "medium", "low"}


def test_advisory_type_has_three_categories() -> None:
    assert {t.value for t in AdvisoryType} == {"eol", "cve", "license"}


def test_advisory_finding_accepts_all_required_fields() -> None:
    finding = AdvisoryFinding(
        plugin_id="com.x",
        plugin_name="X",
        plugin_version="1.0",
        advisory_type=AdvisoryType.CVE,
        severity=Severity.HIGH,
        summary="XSS",
        details="CVE-2024-1",
    )
    assert finding.advisory_type is AdvisoryType.CVE
    assert finding.severity is Severity.HIGH


def test_advisory_set_is_frozen() -> None:
    finding = AdvisoryFinding(
        plugin_id="com.x",
        plugin_name="X",
        plugin_version="1.0",
        advisory_type=AdvisoryType.CVE,
        severity=Severity.HIGH,
        summary="XSS",
        details="CVE-2024-1",
    )
    s = AdvisorySet(findings=())
    with pytest.raises(ValidationError):
        s.findings = (finding,)


def test_plugin_info_accepts_vendor_field() -> None:
    info = PluginInfo(
        plugin_id="com.x",
        name="X",
        version="1.0",
        state="active",
        source="store",
        product_family="ITSM",
        depends_on=(),
        sys_id="abc",
        installed_at=None,
        vendor="Acme Corp",
    )
    assert info.vendor == "Acme Corp"


def test_plugin_info_defaults_vendor_to_empty_string() -> None:
    info = PluginInfo(
        plugin_id="com.x",
        name="X",
        version="1.0",
        state="active",
        source="servicenow",
        product_family="ITSM",
        depends_on=(),
        sys_id="abc",
        installed_at=None,
    )
    assert info.vendor == ""
