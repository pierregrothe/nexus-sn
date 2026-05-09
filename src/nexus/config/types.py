# src/nexus/config/types.py
# Shared primitive types used across all NEXUS layers.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Shared annotated types for use across nexus layers."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import BeforeValidator

__all__ = ["UtcDatetime", "_require_utc"]


def _require_utc(v: object) -> object:
    """Reject naive datetimes and non-UTC offsets before Pydantic coercion.

    Args:
        v: Field value to validate (str or datetime).

    Returns:
        A timezone-aware datetime with UTC offset.

    Raises:
        ValueError: If v is a naive datetime or has a non-UTC offset.
    """
    if isinstance(v, str):
        v = datetime.fromisoformat(v)
    if isinstance(v, datetime) and (v.tzinfo is None or v.utcoffset() != timedelta(0)):
        raise ValueError("datetime must be UTC (tzinfo required, offset must be +00:00)")
    return v


UtcDatetime = Annotated[datetime, BeforeValidator(_require_utc)]
