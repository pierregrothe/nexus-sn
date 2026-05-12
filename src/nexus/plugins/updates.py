# src/nexus/plugins/updates.py
# Update detection for plugin inventories.
# Author: Pierre Grothe
# Date: 2026-05-11
"""plugins_with_updates: filter an inventory down to plugins with a newer version."""

from nexus.plugins.models import PluginInfo, PluginInventory

__all__ = ["plugins_with_updates"]


def plugins_with_updates(inventory: PluginInventory) -> tuple[PluginInfo, ...]:
    """Return plugins whose ``latest_version`` differs from ``version``.

    Filters out:
        - Plugins without ``latest_version`` (typically v_plugin-only
          entries, i.e. core SN plugins).
        - Plugins where ``latest_version == version`` (up to date).

    Args:
        inventory: Plugin inventory captured from an instance.

    Returns:
        Plugins sorted by ``(product_family, plugin_id)`` for stable output.
    """
    updates = [
        p
        for p in inventory.plugins
        if p.latest_version is not None and p.latest_version != p.version
    ]
    updates.sort(key=lambda p: (p.product_family, p.plugin_id))
    return tuple(updates)
