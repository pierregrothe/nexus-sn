# src/nexus/plugins/drift.py
# Single-instance over-time plugin drift detection.
# Author: Pierre Grothe
# Date: 2026-05-12
"""PluginDriftEntry, PluginDriftReport, and compute_drift.

Mirror of ``nexus.plugins.diff`` for single-instance drift: compare
a baseline ``PluginInventory`` against a current one on the same
profile and emit added / removed / version_changed / state_changed
entries.

No I/O: pure functions over already-loaded inventories. The CLI
layer reads the two inventories from disk via the registry.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from nexus.config.types import UtcDatetime
from nexus.plugins.models import PluginInfo, PluginInventory

__all__ = [
    "PluginDriftEntry",
    "PluginDriftReport",
    "compute_drift",
]

_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")


class PluginDriftEntry(BaseModel):
    """One drift row: how a plugin changed between baseline and current.

    Attributes:
        plugin_id: Canonical SN plugin identifier.
        name: Display name (from whichever inventory had the entry).
        product_family: Curated product family or ``Uncategorized``.
        status: Why this row appears. ``version_changed`` wins when
            both version and state changed; the four ``baseline_*``
            / ``current_*`` fields still report both deltas truthfully.
        baseline_version: Version in baseline, or ``None`` when added.
        current_version: Version in current, or ``None`` when removed.
        baseline_state: State in baseline, or ``None`` when added.
        current_state: State in current, or ``None`` when removed.
    """

    model_config = _FROZEN

    plugin_id: str
    name: str
    product_family: str
    status: Literal["added", "removed", "version_changed", "state_changed"]
    baseline_version: str | None
    current_version: str | None
    baseline_state: Literal["active", "inactive"] | None
    current_state: Literal["active", "inactive"] | None


class PluginDriftReport(BaseModel):
    """Drift between a baseline and current inventory for one profile.

    Attributes:
        profile: Instance profile this drift applies to.
        baseline_captured_at: When the baseline inventory was captured.
        current_captured_at: When the current inventory was captured.
        entries: Drift entries in stable ``(product_family, plugin_id)``
            ascending order.
    """

    model_config = _FROZEN

    profile: str
    baseline_captured_at: UtcDatetime
    current_captured_at: UtcDatetime
    entries: tuple[PluginDriftEntry, ...]


def compute_drift(
    baseline: PluginInventory,
    current: PluginInventory,
    profile: str,
) -> PluginDriftReport:
    """Build a drift report from two inventories of the same profile.

    Identical plugins (same ``plugin_id``, ``version``, and ``state``)
    are excluded. Entries are sorted by ``(product_family, plugin_id)``
    ascending for stable output.

    Args:
        baseline: Inventory previously ack'd as the known-good state.
        current: Inventory captured at the most recent refresh.
        profile: Instance profile name (recorded on the report).

    Returns:
        A frozen ``PluginDriftReport`` describing every non-identical plugin.
    """
    by_id_b: dict[str, PluginInfo] = {p.plugin_id: p for p in baseline.plugins}
    by_id_c: dict[str, PluginInfo] = {p.plugin_id: p for p in current.plugins}
    all_ids = sorted(set(by_id_b) | set(by_id_c))
    entries: list[PluginDriftEntry] = []
    for plugin_id in all_ids:
        entry = _drift_entry(plugin_id, by_id_b.get(plugin_id), by_id_c.get(plugin_id))
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda e: (e.product_family, e.plugin_id))
    return PluginDriftReport(
        profile=profile,
        baseline_captured_at=baseline.captured_at,
        current_captured_at=current.captured_at,
        entries=tuple(entries),
    )


def _drift_entry(
    plugin_id: str,
    baseline_info: PluginInfo | None,
    current_info: PluginInfo | None,
) -> PluginDriftEntry | None:
    """Build one PluginDriftEntry for a plugin_id, or None when identical.

    Returns:
        ``None`` when both sides are present with matching version and
        state. Otherwise an entry whose ``status`` is one of
        ``added`` / ``removed`` / ``version_changed`` / ``state_changed``.
    """
    if baseline_info is None and current_info is not None:
        return PluginDriftEntry(
            plugin_id=plugin_id,
            name=current_info.name,
            product_family=current_info.product_family,
            status="added",
            baseline_version=None,
            current_version=current_info.version,
            baseline_state=None,
            current_state=current_info.state,
        )
    if current_info is None and baseline_info is not None:
        return PluginDriftEntry(
            plugin_id=plugin_id,
            name=baseline_info.name,
            product_family=baseline_info.product_family,
            status="removed",
            baseline_version=baseline_info.version,
            current_version=None,
            baseline_state=baseline_info.state,
            current_state=None,
        )
    assert baseline_info is not None
    assert current_info is not None
    if baseline_info.version == current_info.version and baseline_info.state == current_info.state:
        return None
    status: Literal["version_changed", "state_changed"] = (
        "version_changed" if baseline_info.version != current_info.version else "state_changed"
    )
    return PluginDriftEntry(
        plugin_id=plugin_id,
        name=current_info.name,
        product_family=current_info.product_family,
        status=status,
        baseline_version=baseline_info.version,
        current_version=current_info.version,
        baseline_state=baseline_info.state,
        current_state=current_info.state,
    )
