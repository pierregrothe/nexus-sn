# src/nexus/plugins/impact.py
# Plugin impact analysis: reverse-dep graph walk + scope record counts.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Plugin impact analysis layer.

Two-phase design:
    - ``reverse_dependencies`` -- pure BFS over the inventory.
    - Future: ``fetch_scope_record_counts`` (Task 4) -- async aggregate API.
    - Future: ``compute_impact`` (Task 5) -- async orchestrator.
"""

from __future__ import annotations

from collections import deque

from nexus.plugins.errors import PluginImpactError
from nexus.plugins.models import PluginInventory, ReverseDependency

__all__ = ["reverse_dependencies"]


def reverse_dependencies(
    inventory: PluginInventory,
    target: str,
) -> tuple[ReverseDependency, ...]:
    """Walk the reverse dependency graph from ``target``.

    Builds a reverse adjacency map once: ``dependency_id -> set of
    plugin_ids that depend on it``. Then BFS from the target, tracking
    depth and the chain of plugin_ids that lead back to the target. A
    visited set keyed by ``plugin_id`` guards against cycles.

    Args:
        inventory: Captured plugin inventory.
        target: The plugin_id whose dependents we want.

    Returns:
        Tuple of dependents sorted by ``(depth asc, plugin_id asc)``.

    Raises:
        PluginImpactError: If ``target`` is not present in ``inventory``.
    """
    by_id = {p.plugin_id: p for p in inventory.plugins}
    if target not in by_id:
        raise PluginImpactError(target)

    reverse: dict[str, set[str]] = {}
    for plugin in inventory.plugins:
        for dep in plugin.depends_on:
            reverse.setdefault(dep, set()).add(plugin.plugin_id)

    visited: set[str] = {target}
    queue: deque[tuple[str, int, tuple[str, ...]]] = deque()
    queue.append((target, 0, (target,)))

    results: list[ReverseDependency] = []
    while queue:
        current, depth, via = queue.popleft()
        for dependent in reverse.get(current, ()):
            if dependent in visited:
                continue
            visited.add(dependent)
            next_depth = depth + 1
            next_via = (dependent, *via)
            info = by_id[dependent]
            results.append(
                ReverseDependency(
                    plugin_id=dependent,
                    name=info.name,
                    state=info.state,
                    depth=next_depth,
                    via=next_via,
                )
            )
            queue.append((dependent, next_depth, next_via))

    results.sort(key=lambda d: (d.depth, d.plugin_id))
    return tuple(results)
