# tests/test_instances_models.py
# Tests for nexus.instances.errors and nexus.instances.models.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for instance management data models and errors."""

from datetime import UTC, datetime, timedelta, timezone
from typing import get_args

import pytest
from pydantic import ValidationError

from nexus.config.types import UtcDatetime, _require_utc
from nexus.instances.errors import (
    InstanceError,
    InstanceNotFoundError,
    OAuthError,
    SnapshotError,
    TokenExpiredError,
)
from nexus.instances.models import (
    ArtifactRecord,
    InstanceMeta,
    InstanceSnapshot,
    SnapshotCounts,
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
    assert isinstance(counts, SnapshotCounts)
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


def test_instance_not_found_error_is_instance_of_instance_error() -> None:
    assert isinstance(InstanceNotFoundError("x"), InstanceError)


def test_artifact_record_require_utc_rejects_non_utc_datetime() -> None:
    eastern = timezone(timedelta(hours=-5))
    non_utc = datetime.now(eastern)
    with pytest.raises(ValidationError, match="UTC"):
        ArtifactRecord(
            sys_id="x",
            name="x",
            active=True,
            updated_on=non_utc,
            is_custom=False,
        )


def test_instance_snapshot_require_utc_rejects_non_utc_captured_at() -> None:
    eastern = timezone(timedelta(hours=-5))
    non_utc = datetime.now(eastern)
    with pytest.raises(ValidationError, match="UTC"):
        InstanceSnapshot(captured_at=non_utc, sn_version="Xanadu")


def test_instance_meta_require_utc_rejects_non_utc_datetime() -> None:
    eastern = timezone(timedelta(hours=-5))
    non_utc = datetime.now(eastern)
    with pytest.raises(ValidationError, match="UTC"):
        InstanceMeta(
            profile="dev12345",
            url="https://dev12345.service-now.com",
            username="admin",
            client_id="client-123",
            sn_version="Xanadu",
            sn_build="04-01-2025",
            instance_name="dev12345",
            registered_at=non_utc,
            last_connected_at=datetime.now(UTC),
            token_expires_at=datetime.now(UTC),
        )


def test_require_utc_passthrough_with_utc_datetime() -> None:
    dt = datetime.now(UTC)
    assert _require_utc(dt) is dt


def test_require_utc_parses_iso_string_to_datetime() -> None:
    iso = "2026-01-01T00:00:00+00:00"
    result = _require_utc(iso)
    assert isinstance(result, datetime)
    assert result.utcoffset() == timedelta(0)


def test_require_utc_rejects_naive_datetime() -> None:
    naive = datetime(2026, 1, 1, 12, 0, 0)
    with pytest.raises(ValueError, match="UTC"):
        _require_utc(naive)


def test_require_utc_rejects_non_utc_offset() -> None:
    eastern = timezone(timedelta(hours=-5))
    non_utc = datetime(2026, 1, 1, 12, 0, 0, tzinfo=eastern)
    with pytest.raises(ValueError, match="UTC"):
        _require_utc(non_utc)


def test_require_utc_passthrough_with_non_datetime() -> None:
    # Non-datetime, non-string values pass through unchanged (Pydantic handles them).
    assert _require_utc(42) == 42


def test_utc_datetime_alias_is_annotated_type() -> None:
    # UtcDatetime must be an Annotated type wrapping datetime.
    args = get_args(UtcDatetime)
    assert args[0] is datetime
