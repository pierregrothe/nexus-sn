# src/nexus/plugins/impact.py
# Plugin impact analysis: reverse-dep graph walk + scope record counts.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Plugin impact analysis layer.

Three-phase design:
    - ``reverse_dependencies`` -- pure BFS over the inventory.
    - ``fetch_scope_record_counts`` -- async aggregate API call.
    - ``fetch_cross_scope_refs`` -- 3-phase async FK scan across scopes.
    - ``compute_impact`` -- async orchestrator joining the above,
      cache-first against ``PluginInfo.record_counts`` with a
      ``live=True`` opt-in for forced refresh.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque

import httpx

from nexus.plugins.errors import PluginImpactError
from nexus.plugins.models import (
    CrossScopeRef,
    PluginImpact,
    PluginInventory,
    ReverseDependency,
    ScopeRecordCount,
)

__all__ = [
    "ScopeRecordCountError",
    "compute_impact",
    "fetch_cross_scope_refs",
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
        raise ScopeRecordCountError(f"aggregate API returned HTTP {response.status_code}")
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
                entry["value"] for entry in groupby if entry.get("field") == "sys_class_name"
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


_CROSS_SCOPE_CONCURRENCY = 16


async def fetch_cross_scope_refs(
    url: str,
    token: str,
    plugin_id: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[CrossScopeRef, ...]:
    """Find tables in other scopes that reference into ``plugin_id``'s scope.

    Args:
        url: Instance base URL.
        token: OAuth bearer token.
        plugin_id: Target plugin/scope identifier.
        transport: Optional httpx transport for tests.

    Returns:
        Tuple of CrossScopeRef sorted by ``(record_count desc,
        source_scope asc, source_table asc, field asc)``.

    Raises:
        ScopeRecordCountError: When any of the three REST phases fails.
    """
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            base_url=url, headers=headers, timeout=30.0, transport=transport
        ) as client:
            target_tables = await _phase1_target_tables(client, plugin_id)
            inbound = await _phase2_inbound_refs(client, target_tables)
            counts = await _phase3_count_records(client, inbound)
    except httpx.RequestError as exc:
        raise ScopeRecordCountError(f"network error: {exc}") from exc

    refs = [
        CrossScopeRef(
            source_scope=src_scope,
            source_table=src_table,
            field=field,
            target_table=target_table,
            record_count=record_count,
        )
        for (src_scope, src_table, field, target_table), record_count in counts.items()
    ]
    refs.sort(key=lambda r: (-r.record_count, r.source_scope, r.source_table, r.field))
    return tuple(refs)


async def _phase1_target_tables(client: httpx.AsyncClient, plugin_id: str) -> list[str]:
    """Phase 1: list tables in the target plugin's scope.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        plugin_id: Scope identifier.

    Returns:
        List of table names owned by the scope.

    Raises:
        ScopeRecordCountError: On non-200 status or malformed response.
    """
    response = await client.get(
        "/api/now/table/sys_db_object",
        params={
            "sysparm_query": f"sys_scope.scope={plugin_id}",
            "sysparm_fields": "name",
            "sysparm_limit": 200,
        },
    )
    if response.status_code != 200:
        raise ScopeRecordCountError(f"sys_db_object query returned HTTP {response.status_code}")
    try:
        rows = response.json()["result"]
    except (KeyError, ValueError) as exc:
        raise ScopeRecordCountError(f"malformed sys_db_object response: {exc}") from exc
    return [str(r["name"]) for r in rows if r.get("name")]


async def _phase2_inbound_refs(
    client: httpx.AsyncClient, target_tables: list[str]
) -> list[tuple[str, str, str, str]]:
    """Phase 2: for each target table find sys_dictionary rows with internal_type=reference.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        target_tables: Tables owned by the target scope.

    Returns:
        List of (source_scope, source_table, field, target_table) tuples.

    Raises:
        ScopeRecordCountError: On non-200 status or malformed response.
    """
    semaphore = asyncio.Semaphore(_CROSS_SCOPE_CONCURRENCY)

    async def _one(target_table: str) -> list[tuple[str, str, str, str]]:
        async with semaphore:
            response = await client.get(
                "/api/now/table/sys_dictionary",
                params={
                    "sysparm_query": f"internal_type=reference^reference={target_table}",
                    "sysparm_fields": "name,element,sys_scope.scope",
                    "sysparm_limit": 200,
                },
            )
            if response.status_code != 200:
                raise ScopeRecordCountError(
                    f"sys_dictionary query for {target_table} returned HTTP "
                    f"{response.status_code}"
                )
            try:
                rows = response.json()["result"]
            except (KeyError, ValueError) as exc:
                raise ScopeRecordCountError(f"malformed sys_dictionary response: {exc}") from exc
        out: list[tuple[str, str, str, str]] = []
        for r in rows:
            scope_val = r.get("sys_scope.scope", "")
            scope = scope_val if isinstance(scope_val, str) else scope_val.get("value", "")
            out.append((str(scope), str(r["name"]), str(r["element"]), target_table))
        return out

    nested = await asyncio.gather(*(_one(t) for t in target_tables))
    return [item for sub in nested for item in sub]


async def _phase3_count_records(
    client: httpx.AsyncClient, inbound: list[tuple[str, str, str, str]]
) -> dict[tuple[str, str, str, str], int]:
    """Phase 3: for each (src_scope, src_table, field, target_table) tuple count non-null records.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        inbound: List of (source_scope, source_table, field, target_table) tuples.

    Returns:
        Mapping from the tuple to record_count.

    Raises:
        ScopeRecordCountError: On non-200 status or malformed response.
    """
    semaphore = asyncio.Semaphore(_CROSS_SCOPE_CONCURRENCY)

    async def _one(
        ref: tuple[str, str, str, str],
    ) -> tuple[tuple[str, str, str, str], int]:
        _, source_table, field, _ = ref
        async with semaphore:
            response = await client.get(
                f"/api/now/stats/{source_table}",
                params={
                    "sysparm_query": f"{field}ISNOTEMPTY",
                    "sysparm_count": "true",
                },
            )
            if response.status_code != 200:
                raise ScopeRecordCountError(
                    f"stats/{source_table} returned HTTP {response.status_code}"
                )
            try:
                count = int(response.json()["result"]["stats"]["count"])
            except (KeyError, ValueError, TypeError) as exc:
                raise ScopeRecordCountError(
                    f"malformed stats response for {source_table}: {exc}"
                ) from exc
        return ref, count

    pairs = await asyncio.gather(*(_one(r) for r in inbound))
    return dict(pairs)


async def compute_impact(
    inventory: PluginInventory,
    target: str,
    *,
    url: str,
    token: str,
    transport: httpx.AsyncBaseTransport | None = None,
    live: bool = False,
    cross_scope: bool = True,
) -> PluginImpact:
    """Join the reverse-dep graph walk with cached or live record counts.

    Args:
        inventory: Captured plugin inventory.
        target: Plugin to analyze.
        url: Instance base URL.
        token: OAuth bearer token.
        transport: Optional httpx transport for tests.
        live: When True, ignore the cached ``record_counts`` and always
            re-query the live aggregate API. Default False uses cache.
        cross_scope: When True (default), run the 3-phase cross-scope FK
            scan. When False, ``cross_scope_refs`` is empty and
            ``cross_scope_available`` is False.

    Returns:
        PluginImpact with reverse-deps, record counts, and cross-scope refs.

        When ``live=False`` (default) and ``target.record_counts is not
        None``: serves cached breakdown directly, no live call.

        Otherwise: performs the live aggregate call. On failure,
        ``counts_available=False`` and ``record_counts=()``.

    Raises:
        PluginImpactError: If ``target`` is not present in the inventory.
    """
    deps = reverse_dependencies(inventory, target)
    target_info = next(p for p in inventory.plugins if p.plugin_id == target)

    cross_scope_refs: tuple[CrossScopeRef, ...] = ()
    cross_scope_available = False
    if cross_scope:
        try:
            cross_scope_refs = await fetch_cross_scope_refs(url, token, target, transport=transport)
            cross_scope_available = True
        except ScopeRecordCountError as exc:
            log.warning("impact: cross-scope refs unavailable for %s -- %s", target, exc)

    counts: tuple[ScopeRecordCount, ...]
    counts_available: bool
    if not live and target_info.record_counts is not None:
        counts = target_info.record_counts
        counts_available = True
    else:
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
        cross_scope_refs=cross_scope_refs,
        cross_scope_available=cross_scope_available,
    )
