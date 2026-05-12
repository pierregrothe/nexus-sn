# src/nexus/plugins/advisories.py
# EOL / CVE / license advisory checkers and loaders.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Plugin advisory layer: EOL, CVE, and license findings."""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nexus.plugins.models import AdvisoryFinding, AdvisoryType, PluginInfo, Severity

__all__ = ["EolEntry", "_check_eol"]

log = logging.getLogger(__name__)

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class EolEntry(BaseModel):
    """One row of the curated EOL table.

    Attributes:
        plugin_id: SN plugin identifier this entry applies to.
        status: ``end_of_life`` or ``deprecated``.
        effective: Calendar date the status takes effect.
        replacement: Optional successor plugin id.
        notes: Free-form maintainer note rendered into ``details``.
    """

    model_config = _FROZEN

    plugin_id: str
    status: Literal["end_of_life", "deprecated"]
    effective: date
    replacement: str | None = None
    notes: str = ""


def _check_eol(
    plugin: PluginInfo,
    table: dict[str, EolEntry],
    *,
    today: date,
) -> tuple[AdvisoryFinding, ...]:
    """Produce zero or one AdvisoryFinding for a plugin's EOL status.

    Args:
        plugin: The plugin to evaluate.
        table: ``plugin_id -> EolEntry`` lookup.
        today: Reference date for past/future comparison. Injected so tests
            are deterministic; the CLI passes ``datetime.now(UTC).date()``.

    Returns:
        Tuple of at most one AdvisoryFinding (empty when the plugin is not
        listed in ``table``).
    """
    entry = table.get(plugin.plugin_id)
    if entry is None:
        return ()
    if entry.status == "end_of_life" and entry.effective <= today:
        severity = Severity.HIGH
    else:
        severity = Severity.MEDIUM
    label = "End-of-life" if entry.status == "end_of_life" else "Deprecated"
    summary = f"{label} {entry.effective.isoformat()}"
    detail_parts = [summary]
    if entry.replacement:
        detail_parts.append(f"replacement: {entry.replacement}")
    return (
        AdvisoryFinding(
            plugin_id=plugin.plugin_id,
            plugin_name=plugin.name,
            plugin_version=plugin.version,
            advisory_type=AdvisoryType.EOL,
            severity=severity,
            summary=summary,
            details="; ".join(detail_parts),
        ),
    )
