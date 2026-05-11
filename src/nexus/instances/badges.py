# src/nexus/instances/badges.py
# Token TTL -> StatusBadge mapping for instance display surfaces.
# Author: Pierre Grothe
# Date: 2026-05-11
"""token_badge: turn an InstanceMeta's token TTL into a StatusBadge.

Lives in ``instances/`` rather than ``ui/components/`` because it depends
on ``InstanceMeta``. Keeps the generic UI components free of business
types.
"""

from datetime import UTC, datetime

from nexus.instances.models import InstanceMeta
from nexus.ui.components.badge import StatusBadge

__all__ = ["token_badge"]

_WARN_THRESHOLD_MINUTES = 30


def token_badge(meta: InstanceMeta) -> StatusBadge:
    """Build a StatusBadge describing the OAuth token's remaining validity.

    Args:
        meta: Instance metadata with ``token_expires_at``.

    Returns:
        - ``error`` -- token already expired (text ``"EXPIRED"``).
        - ``warn``  -- under 30 minutes remaining (text ``"<n> min left"``).
        - ``ok``    -- 30+ minutes remaining (text ``"<h>h <m>m"`` when an
          hour or more, ``"<n> min"`` when between 30 and 59 minutes).
    """
    now = datetime.now(UTC)
    if now >= meta.token_expires_at:
        return StatusBadge.error("EXPIRED")
    minutes = int((meta.token_expires_at - now).total_seconds() / 60)
    if minutes < _WARN_THRESHOLD_MINUTES:
        return StatusBadge.warn(f"{minutes} min left")
    hours = minutes // 60
    if hours == 0:
        return StatusBadge.ok(f"{minutes} min")
    return StatusBadge.ok(f"{hours}h {minutes % 60}m")
