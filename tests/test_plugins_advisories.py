# tests/test_plugins_advisories.py
# Tests for the plugin advisories layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for src/nexus/plugins/advisories.py and PluginAdvisoryDataError."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import nexus.plugins as pkg
from nexus.plugins.advisories import (
    AdvisoryDatabase,
    CveEntry,
    EolEntry,
    LicensePolicy,
    _check_cves,
    _check_eol,
    _check_license,
    compute_advisories,
)
from nexus.plugins.errors import PluginAdvisoryDataError
from nexus.plugins.models import AdvisoryType, PluginInfo, PluginInventory, Severity
from tests.fakes.fake_advisory_data import make_advisory_database

__all__: list[str] = []


def _info(plugin_id: str = "com.x", version: str = "1.0") -> PluginInfo:
    return PluginInfo(
        plugin_id=plugin_id,
        name="X",
        version=version,
        state="active",
        source="store",
        product_family="ITSM",
        depends_on=(),
        sys_id="abc",
        installed_at=None,
        vendor="Acme Corp",
    )


def test_plugin_advisory_data_error_carries_reason() -> None:
    err = PluginAdvisoryDataError("eol.yaml: parse failed")
    assert str(err) == "eol.yaml: parse failed"


def test_plugin_advisory_data_error_is_exception_subclass() -> None:
    assert issubclass(PluginAdvisoryDataError, Exception)


def test_check_eol_flags_past_effective_date_as_high() -> None:
    table = {
        "com.x": EolEntry(
            plugin_id="com.x",
            status="end_of_life",
            effective=date(2020, 1, 1),
            replacement="com.y",
            notes="replaced",
        ),
    }
    findings = _check_eol(_info(), table, today=date(2026, 5, 11))
    assert len(findings) == 1
    assert findings[0].severity is Severity.HIGH
    assert findings[0].advisory_type is AdvisoryType.EOL
    assert "com.y" in findings[0].details


def test_check_eol_flags_future_effective_date_as_medium() -> None:
    table = {
        "com.x": EolEntry(
            plugin_id="com.x",
            status="end_of_life",
            effective=date(2099, 1, 1),
            replacement=None,
            notes="",
        ),
    }
    findings = _check_eol(_info(), table, today=date(2026, 5, 11))
    assert findings[0].severity is Severity.MEDIUM


def test_check_eol_flags_deprecated_as_medium() -> None:
    table = {
        "com.x": EolEntry(
            plugin_id="com.x",
            status="deprecated",
            effective=date(2020, 1, 1),
            replacement=None,
            notes="",
        ),
    }
    findings = _check_eol(_info(), table, today=date(2026, 5, 11))
    assert findings[0].severity is Severity.MEDIUM


def test_check_eol_returns_empty_when_plugin_absent_from_table() -> None:
    findings = _check_eol(_info(), {}, today=date(2026, 5, 11))
    assert findings == ()


def _cve(
    cve_id: str,
    plugin_id: str,
    severity: Severity,
    spec: str,
    fixed_in: str = "",
) -> CveEntry:
    return CveEntry(
        cve_id=cve_id,
        plugin_id=plugin_id,
        severity=severity,
        affected_versions=spec,
        fixed_in=fixed_in,
        summary=f"Issue {cve_id}",
    )


def test_check_cves_flags_matching_version_in_range() -> None:
    table = {"com.x": (_cve("CVE-1", "com.x", Severity.HIGH, ">=1.0,<2.0", "2.0"),)}
    findings = _check_cves(_info(version="1.5"), table)
    assert len(findings) == 1
    assert findings[0].advisory_type is AdvisoryType.CVE
    assert findings[0].severity is Severity.HIGH
    assert "CVE-1" in findings[0].details


def test_check_cves_skips_version_above_range() -> None:
    table = {"com.x": (_cve("CVE-1", "com.x", Severity.HIGH, ">=1.0,<2.0"),)}
    findings = _check_cves(_info(version="2.5"), table)
    assert findings == ()


def test_check_cves_skips_version_below_range() -> None:
    table = {"com.x": (_cve("CVE-1", "com.x", Severity.HIGH, ">=1.0,<2.0"),)}
    findings = _check_cves(_info(version="0.9"), table)
    assert findings == ()


def test_check_cves_returns_multiple_findings_for_multiple_cves() -> None:
    table = {
        "com.x": (
            _cve("CVE-1", "com.x", Severity.HIGH, ">=1.0"),
            _cve("CVE-2", "com.x", Severity.CRITICAL, ">=1.0"),
        ),
    }
    findings = _check_cves(_info(version="1.5"), table)
    ids = {f.details.split(":")[0].strip() for f in findings}
    assert ids == {"CVE-1", "CVE-2"}


def test_check_cves_skips_unparseable_plugin_version() -> None:
    table = {"com.x": (_cve("CVE-1", "com.x", Severity.HIGH, ">=1.0"),)}
    findings = _check_cves(_info(version="not-a-version-string!!!"), table)
    assert findings == ()


def test_check_license_flags_forbidden_vendor_as_high() -> None:
    policy = LicensePolicy(
        allowed_vendors=("ServiceNow",),
        forbidden_vendors=("Sketchy LLC",),
    )
    sketchy = _info().model_copy(update={"vendor": "Sketchy LLC"})
    findings = _check_license(sketchy, policy)
    assert len(findings) == 1
    assert findings[0].severity is Severity.HIGH
    assert findings[0].advisory_type is AdvisoryType.LICENSE
    assert "Sketchy LLC" in findings[0].details


def test_check_license_flags_unknown_vendor_as_medium() -> None:
    policy = LicensePolicy(allowed_vendors=("ServiceNow",), forbidden_vendors=())
    findings = _check_license(_info(), policy)
    assert len(findings) == 1
    assert findings[0].severity is Severity.MEDIUM


def test_check_license_skips_allowed_vendor() -> None:
    policy = LicensePolicy(allowed_vendors=("Acme Corp",), forbidden_vendors=())
    findings = _check_license(_info(), policy)
    assert findings == ()


def test_check_license_skips_empty_vendor_when_allow_list_empty() -> None:
    policy = LicensePolicy(allowed_vendors=(), forbidden_vendors=())
    no_vendor = _info().model_copy(update={"vendor": ""})
    findings = _check_license(no_vendor, policy)
    assert findings == ()


def test_check_license_skips_empty_vendor_when_allow_list_non_empty() -> None:
    policy = LicensePolicy(allowed_vendors=("ServiceNow",), forbidden_vendors=())
    no_vendor = _info().model_copy(update={"vendor": ""})
    findings = _check_license(no_vendor, policy)
    assert findings == ()


def test_load_database_reads_three_bundled_yamls() -> None:
    db = AdvisoryDatabase.load()
    assert len(db.eol) >= 1
    assert len(db.cves) >= 1
    assert "ServiceNow" in db.licenses.allowed_vendors


def test_load_database_raises_on_malformed_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "eol.yaml").write_text(": : :\n", encoding="utf-8")
    (tmp_path / "cves.yaml").write_text("[]\n", encoding="utf-8")
    (tmp_path / "licenses.yaml").write_text(
        "allowed_vendors: []\nforbidden_vendors: []\n", encoding="utf-8"
    )

    def _fake_path(name: str) -> Path:
        return tmp_path / name

    monkeypatch.setattr("nexus.plugins.advisories._data_path", _fake_path)
    with pytest.raises(PluginAdvisoryDataError):
        AdvisoryDatabase.load()


def test_load_database_raises_on_invalid_cve_specifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "eol.yaml").write_text("[]\n", encoding="utf-8")
    (tmp_path / "cves.yaml").write_text(
        "- cve_id: CVE-X\n"
        "  plugin_id: com.x\n"
        "  severity: high\n"
        "  affected_versions: 'not a valid specifier'\n"
        "  summary: bad\n",
        encoding="utf-8",
    )
    (tmp_path / "licenses.yaml").write_text(
        "allowed_vendors: []\nforbidden_vendors: []\n", encoding="utf-8"
    )

    def _fake_path(name: str) -> Path:
        return tmp_path / name

    monkeypatch.setattr("nexus.plugins.advisories._data_path", _fake_path)
    with pytest.raises(PluginAdvisoryDataError):
        AdvisoryDatabase.load()


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime(2026, 5, 11, tzinfo=UTC),
        sn_version="Washington",
        plugins=plugins,
    )


def test_compute_advisories_returns_empty_set_when_no_findings() -> None:
    db = make_advisory_database()
    inv = _inventory(
        _info("com.unaffected", "1.0").model_copy(update={"vendor": "ServiceNow"}),
    )
    result = compute_advisories(inv, db, today=date(2026, 5, 11))
    assert result.findings == ()


def test_compute_advisories_aggregates_all_three_checker_outputs() -> None:
    db = make_advisory_database()
    inv = _inventory(
        _info("com.cms", "1.5").model_copy(update={"vendor": "Unknown"}),
        _info("com.legacy", "1.0"),
    )
    result = compute_advisories(inv, db, today=date(2026, 5, 11))
    types = {f.advisory_type for f in result.findings}
    assert types == {AdvisoryType.EOL, AdvisoryType.CVE, AdvisoryType.LICENSE}


def test_compute_advisories_sorts_findings_by_severity_then_plugin_id() -> None:
    db = make_advisory_database()
    inv = _inventory(
        _info("com.cms", "1.5").model_copy(update={"vendor": "ServiceNow"}),
        _info("com.legacy", "1.0"),
    )
    result = compute_advisories(inv, db, today=date(2026, 5, 11))
    sev_indices = [
        ("critical", "high", "medium", "low").index(f.severity.value) for f in result.findings
    ]
    assert sev_indices == sorted(sev_indices)
    high_ones = [f for f in result.findings if f.severity is Severity.HIGH]
    plugin_ids = [f.plugin_id for f in high_ones]
    assert plugin_ids == sorted(plugin_ids)


def test_public_api_reexports_advisories_symbols() -> None:
    expected = {
        "AdvisoryDatabase",
        "AdvisoryFinding",
        "AdvisorySet",
        "AdvisoryType",
        "PluginAdvisoryDataError",
        "Severity",
        "compute_advisories",
    }
    assert expected.issubset(set(pkg.__all__))
    for name in expected:
        assert hasattr(pkg, name), f"missing re-export: {name}"
