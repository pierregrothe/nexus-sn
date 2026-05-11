# tests/test_plugins_errors.py
# Tests for the plugins layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for PluginScanError."""

import pytest

from nexus.plugins.errors import PluginScanError

__all__: list[str] = []


def test_plugin_scan_error_holds_reason_and_status() -> None:
    err = PluginScanError("v_plugin", 403)
    assert err.table == "v_plugin"
    assert err.status_code == 403
    assert "v_plugin" in str(err)
    assert "403" in str(err)


def test_plugin_scan_error_is_raisable() -> None:
    with pytest.raises(PluginScanError):
        raise PluginScanError("sys_store_app", 500)
