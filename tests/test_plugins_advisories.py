# tests/test_plugins_advisories.py
# Tests for the plugin advisories layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for src/nexus/plugins/advisories.py and PluginAdvisoryDataError."""

from nexus.plugins.errors import PluginAdvisoryDataError

__all__: list[str] = []


def test_plugin_advisory_data_error_carries_reason() -> None:
    err = PluginAdvisoryDataError("eol.yaml: parse failed")
    assert str(err) == "eol.yaml: parse failed"


def test_plugin_advisory_data_error_is_exception_subclass() -> None:
    assert issubclass(PluginAdvisoryDataError, Exception)
