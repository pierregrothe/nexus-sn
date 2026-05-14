# tests/test_plugins_models_exec.py
# Tests for plugin execution frozen models.
# Author: Pierre Grothe
# Date: 2026-05-14

"""Tests for OperationResult, OperationLog, ProgressState, DependencyEntry."""

import pytest
from pydantic import ValidationError

from nexus.plugins.dependencies import DependencyEntry
from nexus.plugins.executor import OperationLog, OperationResult
from nexus.plugins.progress import ProgressState

__all__: list[str] = []


def test_operation_result_is_frozen() -> None:
    r = OperationResult(
        action="install",
        plugin_id="com.x",
        success=True,
        message="done",
        duration_s=1.2,
        tracker_id="t1",
        update_set=None,
        rollback_version=None,
    )
    with pytest.raises(ValidationError):
        r.success = False  # type: ignore[misc]


def test_operation_result_rejects_unknown_action() -> None:
    with pytest.raises(ValidationError):
        OperationResult(
            action="reboot",
            plugin_id="com.x",
            success=True,
            message="",
            duration_s=0.0,
            tracker_id="t",
            update_set=None,
            rollback_version=None,
        )


def test_operation_log_is_tuple_and_filterable() -> None:
    r1 = OperationResult(
        action="install",
        plugin_id="a",
        success=True,
        message="",
        duration_s=0.0,
        tracker_id="t1",
        update_set=None,
        rollback_version=None,
    )
    r2 = OperationResult(
        action="activate",
        plugin_id="a",
        success=False,
        message="boom",
        duration_s=0.0,
        tracker_id="t2",
        update_set=None,
        rollback_version=None,
    )
    log = OperationLog(results=(r1, r2))
    assert log.success_count == 1
    assert log.failure_count == 1


def test_progress_state_terminal_classification() -> None:
    ps_running = ProgressState.from_sn(
        {
            "status": "1",
            "status_label": "In Progress",
            "percent_complete": 50,
            "error": "",
            "update_set": None,
            "rollback_version": None,
            "trackerId": "t",
            "status_message": "",
            "status_detail": "",
        }
    )
    ps_done = ProgressState.from_sn(
        {
            "status": "2",
            "status_label": "Success",
            "percent_complete": 100,
            "error": "",
            "update_set": None,
            "rollback_version": "1.0",
            "trackerId": "t",
            "status_message": "",
            "status_detail": "",
        }
    )
    ps_failed = ProgressState.from_sn(
        {
            "status": "3",
            "status_label": "Failed",
            "percent_complete": 80,
            "error": "boom",
            "update_set": None,
            "rollback_version": None,
            "trackerId": "t",
            "status_message": "",
            "status_detail": "",
        }
    )
    assert not ps_running.is_terminal
    assert ps_done.is_terminal
    assert ps_done.is_success
    assert ps_failed.is_terminal
    assert not ps_failed.is_success


def test_progress_state_from_progress_poll_shape() -> None:
    """Live capture shape: state/sys_id/string percent_complete, not status/trackerId/int."""
    ps = ProgressState.from_sn(
        {
            "name": "Install from the App Repository",
            "state": "1",
            "message": "Executing queued operation",
            "sys_id": "9e2bd8e23b3803106c7dfa9aa4e45abd",
            "percent_complete": "99",  # STRING
            "updated_on": 1778775777000,
            "results": [],
        }
    )
    assert ps.tracker_id == "9e2bd8e23b3803106c7dfa9aa4e45abd"
    assert ps.status == "1"
    assert ps.percent_complete == 99
    assert not ps.is_terminal


def test_dependency_entry_keeps_servicenow_field_names() -> None:
    d = DependencyEntry(
        id="Vulnerability Response Common",
        orig_string="sn_vul_cmn:2.16.1",
        type="Application",
        min_version="2.16.1",
        source_app_id="abc123",
        installed=True,
        active=True,
        hide_on_ui=False,
        status="Will be Updated",
        status_value="will_be_updated",
        order=2,
        link="nav_to.do?...",
        has_license=False,
        is_allowed_install=True,
    )
    assert d.status_value == "will_be_updated"


def test_dependency_entry_from_sn_handles_id_casing() -> None:
    """SN sends 'Id' with capital I; from_sn normalises to 'id'."""
    raw = {
        "Id": "Security Incident Response",
        "orig_string": "sn_si:13.9.23",
        "type": "Application",
        "minVersion": "13.9.23",
        "source_app_id": "abc",
        "installed": True,
        "active": True,
        "hide_on_ui": False,
        "status": "Installed",
        "status_value": "installed",
        "order": 2,
        "link": "x",
        "has_license": False,
        "is_allowed_install": True,
    }
    d = DependencyEntry.from_sn(raw)
    assert d.id == "Security Incident Response"
    assert d.min_version == "13.9.23"
