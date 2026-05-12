# src/nexus/plugins/overrides.py
# Per-instance advisory override (defer) logic.
# Author: Pierre Grothe
# Date: 2026-05-12
"""AdvisoryOverride, AdvisoryOverrideSet, and apply_overrides."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from nexus.config.types import UtcDatetime
from nexus.plugins.models import AdvisoryFinding, AdvisorySet, AdvisoryType

__all__ = [
    "AdvisoryOverride",
    "AdvisoryOverrideSet",
    "apply_overrides",
]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class AdvisoryOverride(BaseModel):
    """One deferred advisory finding.

    Attributes:
        plugin_id: SN plugin identifier matching ``AdvisoryFinding.plugin_id``.
        advisory_type: Advisory category being deferred.
        details: The exact ``AdvisoryFinding.details`` string identifying the
            specific finding (CVE id, EOL date string, license vendor).
        reason: Free-form non-empty justification.
        created_at: When the override was recorded (UTC).
    """

    model_config = _FROZEN

    plugin_id: str
    advisory_type: AdvisoryType
    details: str
    reason: Annotated[str, Field(min_length=1)]
    created_at: UtcDatetime


class AdvisoryOverrideSet(BaseModel):
    """All overrides for one profile.

    Attributes:
        overrides: Tuple sorted by ``(plugin_id, advisory_type, details)``.
    """

    model_config = _FROZEN

    overrides: tuple[AdvisoryOverride, ...]


def _key(plugin_id: str, advisory_type: AdvisoryType, details: str) -> tuple[str, str, str]:
    """Return the match tuple keyed by the finding's identity triple."""
    return (plugin_id, advisory_type.value, details)


def apply_overrides(
    advisories: AdvisorySet,
    overrides: AdvisoryOverrideSet,
) -> tuple[AdvisorySet, tuple[AdvisoryFinding, ...]]:
    """Split findings into (remaining, deferred) using the override key triple.

    Args:
        advisories: Output from ``compute_advisories``.
        overrides: Loaded override set for the instance.

    Returns:
        ``(remaining, deferred)``. ``remaining`` is an AdvisorySet with all
        non-overridden findings in their original sort order. ``deferred``
        is the tuple of filtered findings in their original sort order.
    """
    keyset = {_key(o.plugin_id, o.advisory_type, o.details) for o in overrides.overrides}
    remaining: list[AdvisoryFinding] = []
    deferred: list[AdvisoryFinding] = []
    for finding in advisories.findings:
        if _key(finding.plugin_id, finding.advisory_type, finding.details) in keyset:
            deferred.append(finding)
        else:
            remaining.append(finding)
    return AdvisorySet(findings=tuple(remaining)), tuple(deferred)
