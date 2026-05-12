# src/nexus/plugins/advisories.py
# EOL / CVE / license advisory checkers and loaders.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Plugin advisory layer: EOL, CVE, and license findings."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from typing import Literal

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion
from packaging.version import parse as parse_version
from pydantic import BaseModel, ConfigDict, field_validator

from nexus.plugins.models import AdvisoryFinding, AdvisoryType, PluginInfo, Severity

__all__ = ["CveEntry", "EolEntry", "_check_cves", "_check_eol"]

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


class CveEntry(BaseModel):
    """One row of the curated CVE table.

    Attributes:
        cve_id: e.g. ``CVE-2024-1234``.
        plugin_id: SN plugin identifier this CVE affects.
        severity: Verbatim from the YAML.
        affected_versions: PEP 440 SpecifierSet string.
        fixed_in: Version string where the issue is resolved; empty if none.
        summary: One-line headline.
    """

    model_config = _FROZEN

    cve_id: str
    plugin_id: str
    severity: Severity
    affected_versions: str
    fixed_in: str = ""
    summary: str

    @field_validator("affected_versions")
    @classmethod
    def _validate_specifier(cls, value: str) -> str:
        """Reject malformed specifier strings at load time."""
        try:
            SpecifierSet(value)
        except InvalidSpecifier as exc:
            raise ValueError(f"invalid SpecifierSet: {value!r}: {exc}") from exc
        return value


def _check_cves(
    plugin: PluginInfo,
    table: Mapping[str, tuple[CveEntry, ...]],
) -> tuple[AdvisoryFinding, ...]:
    """Produce zero or more AdvisoryFindings for known CVEs against ``plugin``.

    Args:
        plugin: The plugin to evaluate.
        table: ``plugin_id -> tuple of CveEntry`` lookup.

    Returns:
        Tuple of AdvisoryFindings, one per matching CVE.
    """
    entries = table.get(plugin.plugin_id, ())
    if not entries:
        return ()
    try:
        version = parse_version(plugin.version)
    except InvalidVersion:
        log.debug(
            "advisories: skipping CVE check for %s -- unparseable version %r",
            plugin.plugin_id,
            plugin.version,
        )
        return ()
    findings: list[AdvisoryFinding] = []
    for entry in entries:
        if version not in SpecifierSet(entry.affected_versions):
            continue
        details = f"{entry.cve_id}: affected {entry.affected_versions}"
        if entry.fixed_in:
            details += f"; fixed in {entry.fixed_in}"
        findings.append(
            AdvisoryFinding(
                plugin_id=plugin.plugin_id,
                plugin_name=plugin.name,
                plugin_version=plugin.version,
                advisory_type=AdvisoryType.CVE,
                severity=entry.severity,
                summary=entry.summary,
                details=details,
            )
        )
    return tuple(findings)
