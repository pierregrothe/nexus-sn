# tests/capture/test_errors.py
# Tests for the capture layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-05-09

from pathlib import Path

from nexus.capture.errors import (
    ArchiveCorruptError,
    CaptureError,
    ScopeNotFoundError,
    TableUnavailableError,
    UpdateSetError,
)


def test_scope_not_found_error_is_capture_error() -> None:
    err = ScopeNotFoundError(scope_id="abc123", instance_id="dev")
    assert isinstance(err, CaptureError)
    assert err.scope_id == "abc123"
    assert err.instance_id == "dev"
    assert "abc123" in str(err)


def test_table_unavailable_error_is_capture_error() -> None:
    err = TableUnavailableError(table="ai_skill", instance_id="dev")
    assert isinstance(err, CaptureError)
    assert err.table == "ai_skill"
    assert err.instance_id == "dev"
    assert "ai_skill" in str(err)


def test_archive_corrupt_error_is_capture_error() -> None:
    archive = Path("/tmp/missing")
    err = ArchiveCorruptError(archive_dir=archive)
    assert isinstance(err, CaptureError)
    assert err.archive_dir == archive
    assert str(archive) in str(err)


def test_update_set_error_is_capture_error() -> None:
    err = UpdateSetError(
        update_set_name="NEXUS-capture",
        instance_id="dev",
        failed_record_sys_id="abc",
        failed_table="ai_skill",
    )
    assert isinstance(err, CaptureError)
    assert err.update_set_name == "NEXUS-capture"
    assert err.instance_id == "dev"
    assert err.failed_record_sys_id == "abc"
    assert err.failed_table == "ai_skill"
    assert "ai_skill" in str(err)
