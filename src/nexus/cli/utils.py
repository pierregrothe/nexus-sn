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

from datetime import UTC, date, datetime

__all__ = ["today", "trunc"]


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
