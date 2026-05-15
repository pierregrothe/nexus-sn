# src/nexus/plugins/filters.py
# Pure-Python family filter helpers for the plugins inventory.
# Author: Pierre Grothe
# Date: 2026-05-14

"""filter_by_family + available_families: in-memory filters over PluginInfo tuples."""

from collections import Counter

from nexus.plugins.models import PluginInfo, ProductFamily

__all__ = ["available_families", "filter_by_family", "unknown_families"]


def filter_by_family(
    plugins: tuple[PluginInfo, ...],
    families: tuple[str, ...],
) -> tuple[PluginInfo, ...]:
    """Return plugins whose ``product_family`` matches any of ``families``.

    Matching is case-insensitive. When ``families`` is empty, the input is
    returned unchanged (no filter applied).

    Args:
        plugins: PluginInfo tuple, typically from PluginInventory or
            plugins_with_updates().
        families: Family names to keep. Empty tuple == no filter.

    Returns:
        Filtered tuple preserving original order.
    """
    if not families:
        return plugins
    wanted = {f.casefold() for f in families}
    return tuple(p for p in plugins if p.product_family.casefold() in wanted)


def unknown_families(requested: tuple[str, ...]) -> tuple[str, ...]:
    """Return names from ``requested`` that are not valid ProductFamily values.

    Matching is case-insensitive (casefold). Used by the CLI to validate
    ``--family`` arguments against the curated taxonomy before filtering.

    Args:
        requested: Family names provided on the command line.

    Returns:
        Tuple of unrecognised names, preserving input order. Empty when
        every requested name is valid.
    """
    valid = {f.value.casefold() for f in ProductFamily}
    return tuple(r for r in requested if r.casefold() not in valid)


def available_families(
    plugins: tuple[PluginInfo, ...],
) -> tuple[tuple[str, int], ...]:
    """Return (family, count) pairs for all distinct families in plugins.

    Args:
        plugins: PluginInfo tuple to scan.

    Returns:
        Tuple of (family_name, plugin_count) sorted by family_name.
    """
    counter: Counter[str] = Counter(p.product_family for p in plugins)
    return tuple(sorted(counter.items(), key=lambda item: item[0].casefold()))
