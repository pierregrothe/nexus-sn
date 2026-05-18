# src/nexus/cli/utils.py
# Tiny shared utilities used by the CLI command modules.
# Author: Pierre Grothe
# Date: 2026-05-16
"""Pure utility helpers shared by every command module.

Extracted from ``cli/__init__.py`` to keep that module marching toward
the 800-line cap defined by ADR-023. Anything stateless, side-effect
free, and used by more than one command goes here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

__all__ = ["humanize_age", "today", "trunc"]


_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 60 * _SECONDS_PER_MINUTE
_SECONDS_PER_DAY = 24 * _SECONDS_PER_HOUR


def humanize_age(delta: timedelta) -> str:
    """Render a ``timedelta`` as a short human-readable age string.

    Output forms (largest non-zero unit plus the next finer one when it
    adds detail):

    * ``< 60s``       -> ``"just now"``
    * ``< 1h``        -> ``"5m ago"``
    * ``< 1d``        -> ``"2h 14m ago"`` (omits minutes when zero)
    * otherwise       -> ``"3d 4h ago"`` (omits hours when zero)

    Negative deltas are clamped to ``"just now"`` so a system-clock skew
    between SN and the host never prints something nonsensical.

    Args:
        delta: Age relative to a captured timestamp (``now - captured_at``).

    Returns:
        Display-only string ending in ``" ago"`` (or the literal ``"just now"``).
    """
    seconds = int(delta.total_seconds())
    if seconds < _SECONDS_PER_MINUTE:
        return "just now"
    if seconds < _SECONDS_PER_HOUR:
        return f"{seconds // _SECONDS_PER_MINUTE}m ago"
    if seconds < _SECONDS_PER_DAY:
        hours, rem = divmod(seconds, _SECONDS_PER_HOUR)
        minutes = rem // _SECONDS_PER_MINUTE
        return f"{hours}h {minutes}m ago" if minutes else f"{hours}h ago"
    days, rem = divmod(seconds, _SECONDS_PER_DAY)
    hours = rem // _SECONDS_PER_HOUR
    return f"{days}d {hours}h ago" if hours else f"{days}d ago"


def today() -> date:
    """Current UTC calendar date. Single point for monkeypatching in tests."""
    return datetime.now(UTC).date()


def trunc(s: str, width: int) -> str:
    """Truncate ``s`` to ``width`` characters, appending an ellipsis if needed.

    Args:
        s: Source string.
        width: Maximum width including the ellipsis.

    Returns:
        ``s`` unchanged if its length fits, otherwise the first ``width - 3``
        characters followed by ``"..."``.
    """
    return s if len(s) <= width else s[: width - 3] + "..."
