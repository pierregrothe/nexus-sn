# tests/test_plugins_impact.py
# Tests for the plugin impact analysis layer.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for src/nexus/plugins/impact.py and PluginImpactError."""

from nexus.plugins.errors import PluginImpactError

__all__: list[str] = []


def test_plugin_impact_error_carries_plugin_id() -> None:
    err = PluginImpactError("com.unknown")
    assert err.plugin_id == "com.unknown"
    assert "com.unknown" in str(err)


def test_plugin_impact_error_is_exception_subclass() -> None:
    assert issubclass(PluginImpactError, Exception)
