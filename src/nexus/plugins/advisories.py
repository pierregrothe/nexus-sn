# src/nexus/plugins/advisories.py
# EOL / CVE / license advisory checkers and loaders.
# Author: Pierre Grothe
# Date: 2026-05-11
"""Plugin advisory layer: EOL, CVE, and license findings."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion
from packaging.version import parse as parse_version
from pydantic import BaseModel, ConfigDict, field_validator

from nexus.plugins.errors import PluginAdvisoryDataError
from nexus.plugins.models import AdvisoryFinding, AdvisoryType, PluginInfo, Severity

__all__ = [
    "AdvisoryDatabase",
    "CveEntry",
    "EolEntry",
    "LicensePolicy",
    "_check_cves",
    "_check_eol",
    "_check_license",
]

log = logging.getLogger(__name__)

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


def _data_path(name: str) -> Path:
    """Return the path to a bundled advisory YAML file.

    Args:
        name: Filename within ``src/nexus/plugins/data/``.

    Returns:
        Absolute path to the bundled YAML.
    """
    return Path(__file__).parent / "data" / name


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


class LicensePolicy(BaseModel):
    """Vendor allow / forbid lists for license findings.

    Attributes:
        allowed_vendors: Vendors that always pass the license check.
        forbidden_vendors: Vendors that always trigger a high-severity finding.
    """

    model_config = _FROZEN

    allowed_vendors: tuple[str, ...]
    forbidden_vendors: tuple[str, ...]


def _check_license(
    plugin: PluginInfo,
    policy: LicensePolicy,
) -> tuple[AdvisoryFinding, ...]:
    """Produce zero or one AdvisoryFinding for the plugin's vendor.

    Severity rules:
        - Empty ``plugin.vendor`` -> no finding (no signal).
        - Vendor in ``policy.forbidden_vendors`` -> HIGH.
        - Vendor in ``policy.allowed_vendors`` -> no finding.
        - Vendor non-empty, absent from both, ``allowed_vendors`` non-empty -> MEDIUM.
        - Vendor non-empty, absent from both, ``allowed_vendors`` empty -> no finding.

    Args:
        plugin: The plugin to evaluate.
        policy: Allow / forbid lists.

    Returns:
        Tuple of at most one AdvisoryFinding.
    """
    vendor = plugin.vendor
    if not vendor:
        return ()
    if vendor in policy.forbidden_vendors:
        severity = Severity.HIGH
        summary = "Forbidden vendor"
    elif vendor in policy.allowed_vendors:
        return ()
    elif policy.allowed_vendors:
        severity = Severity.MEDIUM
        summary = "Vendor not in allow-list"
    else:
        return ()
    return (
        AdvisoryFinding(
            plugin_id=plugin.plugin_id,
            plugin_name=plugin.name,
            plugin_version=plugin.version,
            advisory_type=AdvisoryType.LICENSE,
            severity=severity,
            summary=summary,
            details=f"vendor: {vendor}",
        ),
    )


class AdvisoryDatabase(BaseModel):
    """Loaded contents of the three bundled advisory YAML files.

    Attributes:
        eol: ``plugin_id -> EolEntry`` lookup.
        cves: ``plugin_id -> tuple of CveEntry`` lookup.
        licenses: Vendor allow/forbid policy.
    """

    model_config = _FROZEN

    eol: dict[str, EolEntry]
    cves: dict[str, tuple[CveEntry, ...]]
    licenses: LicensePolicy

    @classmethod
    def load(cls) -> AdvisoryDatabase:
        """Read the three bundled YAML files and validate them.

        Returns:
            Parsed AdvisoryDatabase.

        Raises:
            PluginAdvisoryDataError: If any file is missing, malformed,
                or fails schema validation.
        """
        try:
            eol_raw: list[dict[str, object]] = (
                yaml.safe_load(_data_path("eol.yaml").read_text(encoding="utf-8")) or []
            )
            cves_raw: list[dict[str, object]] = (
                yaml.safe_load(_data_path("cves.yaml").read_text(encoding="utf-8")) or []
            )
            licenses_raw: dict[str, list[str]] = (
                yaml.safe_load(_data_path("licenses.yaml").read_text(encoding="utf-8")) or {}
            )
            eol_entries = [EolEntry.model_validate(row) for row in eol_raw]
            cve_entries: list[CveEntry] = []
            for row in cves_raw:
                normalized = dict(row)
                severity_value = normalized.get("severity")
                if isinstance(severity_value, str):
                    normalized["severity"] = Severity(severity_value)
                cve_entries.append(CveEntry.model_validate(normalized))
            licenses = LicensePolicy.model_validate(
                {
                    "allowed_vendors": tuple(licenses_raw.get("allowed_vendors") or []),
                    "forbidden_vendors": tuple(licenses_raw.get("forbidden_vendors") or []),
                }
            )
        except Exception as exc:
            raise PluginAdvisoryDataError(f"failed to load advisory data: {exc}") from exc

        eol_by_id: dict[str, EolEntry] = {e.plugin_id: e for e in eol_entries}
        cves_by_id: dict[str, tuple[CveEntry, ...]] = {}
        for entry in cve_entries:
            cves_by_id[entry.plugin_id] = (*cves_by_id.get(entry.plugin_id, ()), entry)
        return cls(eol=eol_by_id, cves=cves_by_id, licenses=licenses)
