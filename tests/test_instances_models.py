# tests/test_instances_models.py
# Tests for nexus.instances.errors and nexus.instances.models.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for instance management data models and errors."""

from datetime import UTC, datetime

from nexus.instances.errors import (
    InstanceNotFoundError,
    OAuthError,
    SnapshotError,
    TokenExpiredError,
)
from nexus.instances.models import (
    ArtifactRecord,
    InstanceMeta,
    InstanceSnapshot,
)


def test_instance_not_found_error_message_contains_profile() -> None:
    err = InstanceNotFoundError("dev12345")
    assert "dev12345" in str(err)
    assert err.profile == "dev12345"


def test_oauth_error_message_contains_description() -> None:
    err = OAuthError("invalid_grant")
    assert "invalid_grant" in str(err)


def test_token_expired_error_message_contains_profile() -> None:
    err = TokenExpiredError("dev12345")
    assert "dev12345" in str(err)
    assert err.profile == "dev12345"


def test_snapshot_error_stores_table_and_status() -> None:
    err = SnapshotError("sys_script", 403)
    assert "sys_script" in str(err)
    assert "403" in str(err)
    assert err.table == "sys_script"
    assert err.status_code == 403


def test_instance_meta_create_sets_timestamps() -> None:
    meta = InstanceMeta.create(
        profile="dev12345",
        url="https://dev12345.service-now.com",
        username="admin",
        client_id="client-123",
        sn_version="Xanadu",
        sn_build="04-01-2025",
        instance_name="dev12345",
        token_expires_in=1800,
    )
    assert meta.profile == "dev12345"
    assert meta.sn_version == "Xanadu"
    delta = meta.token_expires_at - meta.registered_at
    assert abs(delta.total_seconds() - 1800) < 2


def test_instance_meta_create_registered_equals_last_connected() -> None:
    meta = InstanceMeta.create(
        profile="dev12345",
        url="https://dev12345.service-now.com",
        username="admin",
        client_id="client-123",
        sn_version="Xanadu",
        sn_build="04-01-2025",
        instance_name="dev12345",
        token_expires_in=1800,
    )
    assert meta.registered_at == meta.last_connected_at


def test_instance_snapshot_counts_returns_totals() -> None:
    record = ArtifactRecord(
        sys_id="abc",
        name="Test",
        active=True,
        updated_on=datetime.now(UTC),
        is_custom=True,
    )
    snapshot = InstanceSnapshot(
        captured_at=datetime.now(UTC),
        sn_version="Xanadu",
        ai_skills=[record],
        flows=[record, record],
    )
    counts = snapshot.counts
    assert counts.ai_skills == 1
    assert counts.flows == 2
    assert counts.business_rules == 0
    assert counts.script_includes == 0


def test_artifact_record_extra_accepts_mixed_types() -> None:
    record = ArtifactRecord(
        sys_id="abc",
        name="Test",
        active=True,
        updated_on=datetime.now(UTC),
        is_custom=False,
        extra={"skill_type": "now_assist", "client_callable": False, "order": 100},
    )
    assert record.extra["skill_type"] == "now_assist"
    assert record.extra["client_callable"] is False
    assert record.extra["order"] == 100
