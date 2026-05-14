# tests/test_plugins_errors.py
# Tests for the plugins layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for plugin error types."""

import pytest

from nexus.plugins.errors import (
    PluginBaselineNotFoundError,
    PluginBatchError,
    PluginExecutionError,
    PluginNotFoundError,
    PluginProgressError,
    PluginScanError,
    PluginTimeoutError,
)

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


def test_plugin_baseline_not_found_error_holds_profile() -> None:
    err = PluginBaselineNotFoundError("prod")
    assert err.profile == "prod"
    assert "prod" in str(err)
    assert "baseline" in str(err)


def test_plugin_baseline_not_found_error_is_raisable() -> None:
    with pytest.raises(PluginBaselineNotFoundError):
        raise PluginBaselineNotFoundError("dev")


def test_plugin_progress_error_carries_tracker_and_status() -> None:
    err = PluginProgressError(tracker_id="abc", sn_status="3", error_message="boom")
    assert err.tracker_id == "abc"
    assert err.sn_status == "3"
    assert err.error_message == "boom"
    assert isinstance(err, PluginExecutionError)


def test_plugin_timeout_error_carries_elapsed_seconds() -> None:
    err = PluginTimeoutError(tracker_id="xyz", elapsed_s=600.0)
    assert err.tracker_id == "xyz"
    assert err.elapsed_s == 600.0
    assert isinstance(err, PluginExecutionError)


def test_plugin_not_found_error_carries_plugin_id() -> None:
    err = PluginNotFoundError("com.snc.missing")
    assert err.plugin_id == "com.snc.missing"
    assert "com.snc.missing" in str(err)
    assert isinstance(err, PluginExecutionError)


def test_plugin_batch_error_preserves_response_fragment() -> None:
    err = PluginBatchError(batch_response="--boundary\r\nbad")
    assert "boundary" in err.batch_response
    assert isinstance(err, PluginExecutionError)
