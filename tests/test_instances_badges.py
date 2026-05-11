# tests/test_instances_badges.py
# Tests for the token_badge helper.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Tests for nexus.instances.badges.token_badge."""

from datetime import UTC, datetime, timedelta

from nexus.instances.badges import token_badge
from nexus.instances.models import InstanceMeta
from nexus.ui.components.badge import StatusBadge

__all__: list[str] = []


def _meta(token_expires_at: datetime) -> InstanceMeta:
    now = datetime.now(UTC)
    return InstanceMeta(
        profile="dev",
        url="https://dev.service-now.com",
        username="admin",
        client_id="cid",
        sn_version="Xanadu",
        sn_build="04-01-2025_1200",
        instance_name="dev",
        registered_at=now,
        last_connected_at=now,
        token_expires_at=token_expires_at,
    )


def test_token_badge_returns_error_when_expired() -> None:
    badge = token_badge(_meta(datetime.now(UTC) - timedelta(minutes=1)))
    assert isinstance(badge, StatusBadge)
    assert badge.variant == "error"
    assert badge.text == "EXPIRED"


def test_token_badge_returns_warn_when_under_thirty_minutes() -> None:
    badge = token_badge(_meta(datetime.now(UTC) + timedelta(minutes=10)))
    assert badge.variant == "warn"
    assert "min left" in badge.text


def test_token_badge_returns_ok_when_hours_remaining() -> None:
    badge = token_badge(_meta(datetime.now(UTC) + timedelta(hours=3, minutes=15)))
    assert badge.variant == "ok"
    assert "h" in badge.text


def test_token_badge_returns_ok_minutes_when_between_thirty_and_sixty() -> None:
    badge = token_badge(_meta(datetime.now(UTC) + timedelta(minutes=45)))
    assert badge.variant == "ok"
    assert badge.text.endswith("min")
