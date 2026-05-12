# src/nexus/plugins/models.py
# Pydantic models for the ServiceNow plugin inventory layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""PluginInfo, PluginInventory, ProductFamily."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from nexus.config.types import UtcDatetime

__all__ = [
    "AdvisoryFinding",
    "AdvisorySet",
    "AdvisoryType",
    "PluginImpact",
    "PluginInfo",
    "PluginInventory",
    "ProductFamily",
    "ReverseDependency",
    "ScopeRecordCount",
    "Severity",
    "total_records",
]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class ProductFamily(StrEnum):
    """ServiceNow product taxonomy used by the inventory filter."""

    ITSM = "ITSM"
    ITOM = "ITOM"
    ITAM = "ITAM"
    SPM = "SPM"
    CSM = "CSM"
    HRSD = "HRSD"
    FSM = "FSM"
    GRC = "GRC"
    IRM = "IRM"
    SEC_OPS = "SecOps"
    PLATFORM = "Platform"
    UNCATEGORIZED = "Uncategorized"


class PluginInfo(BaseModel):
    """One plugin's static metadata on an instance.

    Attributes:
        plugin_id: Canonical SN plugin identifier (e.g. ``com.snc.incident``).
        name: Display name from sys_store_app.name or v_plugin.name.
        version: Currently installed version string.
        state: ``active`` if activated, ``inactive`` otherwise.
        source: Origin of the plugin record.
        product_family: Curated product family or ``Uncategorized``.
        depends_on: Direct plugin dependencies (no traversal at this layer).
        sys_id: SN record sys_id.
        installed_at: Activation timestamp; ``None`` if never activated.
        latest_version: The newest available version per ``sys_store_app``;
            ``None`` for v_plugin-only records (core SN plugins) and for
            store apps where the field is empty.
        vendor: Publisher name from ``sys_store_app.vendor``. Empty string
            for v_plugin-only records or when the field is absent.
        record_counts: Per-table record counts owned by this plugin's
            scope, sorted by ``(count desc, table asc)``. ``None`` when
            uncaptured. Empty tuple means the scope owns zero records.
    """

    model_config = _FROZEN

    plugin_id: str
    name: str
    version: str
    state: Literal["active", "inactive"]
    source: Literal["servicenow", "store", "custom"]
    product_family: str
    depends_on: tuple[str, ...]
    sys_id: str
    installed_at: UtcDatetime | None
    latest_version: str | None = None
    vendor: str = ""
    record_counts: tuple[ScopeRecordCount, ...] | None = None


class PluginInventory(BaseModel):
    """Plugin inventory captured from one instance at a single moment.

    Attributes:
        captured_at: When the scan ran (UTC).
        sn_version: SN release name at scan time, copied from InstanceMeta.
        plugins: All plugins discovered on the instance.
    """

    model_config = _FROZEN

    captured_at: UtcDatetime
    sn_version: str
    plugins: tuple[PluginInfo, ...]


class Severity(StrEnum):
    """Normalized severity for advisory findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AdvisoryType(StrEnum):
    """The three advisory categories surfaced by ``nexus plugins advisories``."""

    EOL = "eol"
    CVE = "cve"
    LICENSE = "license"


class AdvisoryFinding(BaseModel):
    """One advisory hit on one plugin.

    Attributes:
        plugin_id: SN plugin identifier.
        plugin_name: Display name copied from the inventory.
        plugin_version: Installed version copied from the inventory.
        advisory_type: Which checker produced this finding.
        severity: Normalized severity.
        summary: One-line headline rendered as a table cell.
        details: Type-specific detail (CVE id, EOL date, vendor name).
    """

    model_config = _FROZEN

    plugin_id: str
    plugin_name: str
    plugin_version: str
    advisory_type: AdvisoryType
    severity: Severity
    summary: str
    details: str


class AdvisorySet(BaseModel):
    """All findings produced by one advisory scan over an inventory.

    Attributes:
        findings: All findings, ordered by ``(severity desc, plugin_id asc)``.
    """

    model_config = _FROZEN

    findings: tuple[AdvisoryFinding, ...]


class ReverseDependency(BaseModel):
    """One plugin that transitively depends on an impact target.

    Attributes:
        plugin_id: SN plugin identifier.
        name: Display name from the inventory.
        state: ``active`` or ``inactive`` -- copied from PluginInfo.
        depth: 1 = direct dependent, 2 = depends on a direct, etc.
        via: Chain of plugin_ids from this plugin back to the target,
            inclusive of both endpoints. Length is ``depth + 1``.
    """

    model_config = _FROZEN

    plugin_id: str
    name: str
    state: Literal["active", "inactive"]
    depth: int
    via: tuple[str, ...]


class ScopeRecordCount(BaseModel):
    """One row of the aggregate query over sys_metadata.

    Attributes:
        table: ``sys_class_name`` of the records (e.g. ``sys_script``).
        count: Number of records in the target plugin's scope owned
            by this table. Always >= 0.
    """

    model_config = _FROZEN

    table: str
    count: Annotated[int, Field(ge=0)]


class PluginImpact(BaseModel):
    """Full impact analysis result for one plugin.

    Attributes:
        target_plugin_id: Plugin the user asked about.
        target_name: Display name of the target.
        reverse_deps: All plugins that depend on the target,
            sorted by ``(depth asc, plugin_id asc)``.
        record_counts: Per-table record counts owned by the target's
            scope, sorted by ``(count desc, table asc)``. Empty tuple
            when the live REST call was skipped or failed.
        counts_available: ``True`` if the record-count REST call
            succeeded; ``False`` on any network/4xx/5xx/parse error.
    """

    model_config = _FROZEN

    target_plugin_id: str
    target_name: str
    reverse_deps: tuple[ReverseDependency, ...]
    record_counts: tuple[ScopeRecordCount, ...]
    counts_available: bool


def total_records(info: PluginInfo) -> int | None:
    """Sum of cached per-table record counts, or ``None`` when uncaptured.

    Args:
        info: PluginInfo whose cached counts to sum.

    Returns:
        Total record count, ``0`` when ``record_counts`` is an empty tuple,
        or ``None`` when ``record_counts`` is ``None``.
    """
    if info.record_counts is None:
        return None
    return sum(c.count for c in info.record_counts)
