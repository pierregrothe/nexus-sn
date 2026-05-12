# src/nexus/plugins/orphans.py
# Orphan plugin detection over a captured inventory.
# Author: Pierre Grothe
# Date: 2026-05-12
"""orphan_candidates: filter to plugins with zero deps and zero records."""

from nexus.plugins.models import PluginInfo, PluginInventory, total_records

__all__ = ["orphan_candidates"]


def orphan_candidates(inventory: PluginInventory) -> tuple[PluginInfo, ...]:
    """Return plugins with no dependents and no scope-owned records.

    Plugins with ``record_counts is None`` (not captured yet) are
    excluded -- the criterion requires evidence of zero records,
    not absence of data.

    Args:
        inventory: Captured plugin inventory.

    Returns:
        Tuple of orphan plugins sorted by ``(state asc, plugin_id asc)``.
        Active plugins sort before inactive plugins alphabetically.
    """
    has_dependents: set[str] = set()
    for plugin in inventory.plugins:
        for dep in plugin.depends_on:
            has_dependents.add(dep)
    orphans = [
        p for p in inventory.plugins if p.plugin_id not in has_dependents and total_records(p) == 0
    ]
    orphans.sort(key=lambda p: (p.state, p.plugin_id))
    return tuple(orphans)
