# tests/test_plugins_advisories.py
# Tests for the plugin advisories layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for src/nexus/plugins/advisories.py and PluginAdvisoryDataError."""

from datetime import date

from nexus.plugins.advisories import EolEntry, _check_eol
from nexus.plugins.errors import PluginAdvisoryDataError
from nexus.plugins.models import AdvisoryType, PluginInfo, Severity

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
