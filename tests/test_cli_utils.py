# tests/test_cli_utils.py
# Unit tests for cli/utils.py helpers.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Tests for the pure utility helpers shared across CLI command modules."""

from __future__ import annotations

from datetime import timedelta

from nexus.cli.utils import humanize_age, trunc

__all__: list[str] = []


def test_humanize_age_returns_just_now_for_sub_minute_delta() -> None:
    assert humanize_age(timedelta(seconds=30)) == "just now"


def test_humanize_age_returns_just_now_for_negative_delta() -> None:
    """Clock skew between SN and host must not surface nonsense like '-5m ago'."""
    assert humanize_age(timedelta(seconds=-10)) == "just now"


def test_humanize_age_renders_minutes_only_under_one_hour() -> None:
    assert humanize_age(timedelta(minutes=5)) == "5m ago"


def test_humanize_age_renders_hours_and_minutes_under_one_day() -> None:
    assert humanize_age(timedelta(hours=2, minutes=14)) == "2h 14m ago"


def test_humanize_age_drops_zero_minutes_under_one_day() -> None:
    assert humanize_age(timedelta(hours=3)) == "3h ago"


def test_humanize_age_renders_days_and_hours_over_one_day() -> None:
    assert humanize_age(timedelta(days=3, hours=4)) == "3d 4h ago"


def test_humanize_age_drops_zero_hours_over_one_day() -> None:
    assert humanize_age(timedelta(days=7)) == "7d ago"


def test_trunc_returns_string_unchanged_when_under_width() -> None:
    assert trunc("hello", 10) == "hello"


def test_trunc_appends_ellipsis_when_over_width() -> None:
    assert trunc("hello world", 8) == "hello..."
