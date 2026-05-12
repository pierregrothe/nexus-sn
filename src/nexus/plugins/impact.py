# src/nexus/plugins/impact.py
# Plugin impact analysis: reverse-dep graph walk + scope record counts.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Plugin impact analysis layer.

Three-phase design:
    - ``reverse_dependencies`` -- pure BFS over the inventory.
    - ``fetch_scope_record_counts`` -- async aggregate API call.
    - ``compute_impact`` -- async orchestrator joining the two.
"""

from __future__ import annotations

import logging
from collections import deque

import httpx

from nexus.plugins.errors import PluginImpactError
from nexus.plugins.models import (
    PluginImpact,
    PluginInventory,
    ReverseDependency,
    ScopeRecordCount,
)

__all__ = [
    "ScopeRecordCountError",
    "compute_impact",
    "fetch_scope_counts_with_client",
    "fetch_scope_record_counts",
    "reverse_dependencies",
]

log = logging.getLogger(__name__)


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


class ScopeRecordCountError(Exception):
    """Raised when the live aggregate REST call fails or is unparseable.

    Internal to ``impact.py``; not surfaced at the public ``nexus.plugins``
    layer. ``compute_impact`` catches it to set ``counts_available=False``.
    """


async def fetch_scope_counts_with_client(
    client: httpx.AsyncClient,
    plugin_id: str,
) -> tuple[ScopeRecordCount, ...]:
    """Aggregate query over sys_metadata using an existing client.

    Shared inner helper. ``fetch_scope_record_counts`` wraps this with
    its own client; ``scanner._sum_scope_records`` calls this directly
    with its scan-time client and sums the buckets.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        plugin_id: Scope identifier (e.g. ``com.snc.incident``).

    Returns:
        Per-table counts sorted by ``(count desc, table asc)``.

    Raises:
        ScopeRecordCountError: On non-200 status or malformed response.
    """
    params = {
        "sysparm_query": f"sys_scope.scope={plugin_id}",
        "sysparm_count": "true",
        "sysparm_group_by": "sys_class_name",
    }
    response = await client.get("/api/now/stats/sys_metadata", params=params)
    if response.status_code != 200:
        raise ScopeRecordCountError(
            f"aggregate API returned HTTP {response.status_code}"
        )
    try:
        payload = response.json()
        rows = payload["result"]
    except (KeyError, ValueError) as exc:
        raise ScopeRecordCountError(f"malformed response: {exc}") from exc

    counts: list[ScopeRecordCount] = []
    for row in rows:
        try:
            stats = row["stats"]
            count = int(stats["count"])
            groupby = row["groupby_fields"]
            table = next(
                entry["value"]
                for entry in groupby
                if entry.get("field") == "sys_class_name"
            )
        except (KeyError, StopIteration, TypeError, ValueError) as exc:
            raise ScopeRecordCountError(f"malformed row: {exc}") from exc
        counts.append(ScopeRecordCount(table=table, count=count))

    counts.sort(key=lambda c: (-c.count, c.table))
    return tuple(counts)


async def fetch_scope_record_counts(
    url: str,
    token: str,
    plugin_id: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[ScopeRecordCount, ...]:
    """Live aggregate query over ``sys_metadata``.

    Args:
        url: Instance base URL.
        token: OAuth bearer token.
        plugin_id: Plugin scope to count records for.
        transport: Optional httpx transport for tests.

    Returns:
        Per-table counts sorted by ``(count desc, table asc)``.

    Raises:
        ScopeRecordCountError: On non-200 status, network error, or
            malformed response.
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            base_url=url,
            headers=headers,
            timeout=30.0,
            transport=transport,
        ) as client:
            return await fetch_scope_counts_with_client(client, plugin_id)
    except httpx.RequestError as exc:
        raise ScopeRecordCountError(f"network error: {exc}") from exc


async def compute_impact(
    inventory: PluginInventory,
    target: str,
    *,
    url: str,
    token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PluginImpact:
    """Join the reverse-dep graph walk and the live aggregate call.

    Args:
        inventory: Captured plugin inventory.
        target: Plugin to analyze.
        url: Instance base URL.
        token: OAuth bearer token.
        transport: Optional httpx transport for tests.

    Returns:
        PluginImpact with reverse-deps and record counts. If the
        Aggregate API call fails, ``counts_available`` is False and
        ``record_counts`` is empty; the reverse-deps section is
        unaffected.

    Raises:
        PluginImpactError: If ``target`` is not present in the inventory.
    """
    deps = reverse_dependencies(inventory, target)
    target_info = next(p for p in inventory.plugins if p.plugin_id == target)
    try:
        counts = await fetch_scope_record_counts(url, token, target, transport=transport)
        counts_available = True
    except ScopeRecordCountError as exc:
        log.warning("impact: counts unavailable for %s -- %s", target, exc)
        counts = ()
        counts_available = False
    return PluginImpact(
        target_plugin_id=target,
        target_name=target_info.name,
        reverse_deps=deps,
        record_counts=counts,
        counts_available=counts_available,
    )
