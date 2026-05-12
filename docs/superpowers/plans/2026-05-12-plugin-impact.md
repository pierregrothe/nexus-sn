# Plugin Impact Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `nexus plugins impact <plugin_id>`, a CLI command that shows the transitive reverse-dependency closure of a plugin (from the cached inventory) plus per-table record counts in the plugin's scope (live Aggregate API call).

**Architecture:** Two-phase design. Phase 1: pure synchronous BFS over the in-memory plugin inventory yields a `tuple[ReverseDependency, ...]`. Phase 2: async REST call to `/api/now/stats/sys_metadata` yields a `tuple[ScopeRecordCount, ...]`. An async `compute_impact` joins them. CLI command wires up token retrieval (existing `_acquire_token` helper), prints two DataTables and a summary Notice. Live REST failures degrade gracefully -- reverse-deps still ship, counts marked unavailable.

**Tech Stack:** Python 3.14, Pydantic v2 (frozen+strict+extra=forbid), `httpx.AsyncClient` + `httpx.MockTransport` for tests, Typer, Rich.

**Branch:** `feat/plugins-impact` (stacked on PR #14 -- `feat/plugins-advisories`).

**Spec:** `docs/superpowers/specs/2026-05-12-plugin-impact-design.md`

---

## File Map

**Create:**
- `src/nexus/plugins/impact.py` -- `reverse_dependencies`, `fetch_scope_record_counts`, `compute_impact`, private `ScopeRecordCountError`
- `tests/test_plugins_impact.py`
- `tests/test_cli_plugins_impact.py`

**Modify:**
- `src/nexus/plugins/models.py` -- add `ReverseDependency`, `ScopeRecordCount`, `PluginImpact`
- `src/nexus/plugins/errors.py` -- add `PluginImpactError`
- `src/nexus/plugins/__init__.py` -- re-export new symbols
- `src/nexus/cli.py` -- new `impact` subcommand + update `_PLUGINS_HELP`
- `tests/test_plugins_models.py` -- 3 new tests
- `.ratchet.json` -- new baselines + cli.py bump

---

## Task 1: ReverseDependency / ScopeRecordCount / PluginImpact models

**Files:**
- Modify: `src/nexus/plugins/models.py`
- Modify: `tests/test_plugins_models.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_models.py`:

```python
from nexus.plugins.models import (
    PluginImpact,
    ReverseDependency,
    ScopeRecordCount,
)


def test_reverse_dependency_accepts_all_required_fields() -> None:
    dep = ReverseDependency(
        plugin_id="com.dependent",
        name="Dependent",
        state="active",
        depth=2,
        via=("com.dependent", "com.middle", "com.target"),
    )
    assert dep.depth == 2
    assert dep.via[-1] == "com.target"


def test_scope_record_count_rejects_negative_count() -> None:
    with pytest.raises(ValidationError):
        ScopeRecordCount(table="sys_script", count=-1)


def test_plugin_impact_is_frozen() -> None:
    impact = PluginImpact(
        target_plugin_id="com.x",
        target_name="X",
        reverse_deps=(),
        record_counts=(),
        counts_available=False,
    )
    with pytest.raises(ValidationError):
        impact.target_name = "Y"
```

- [ ] **Step 2: Run tests; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_models.py -v -k "reverse_dependency or scope_record_count or plugin_impact"`

Expected: ImportError on the three new symbols.

- [ ] **Step 3: Add the three models to `src/nexus/plugins/models.py`**

Add `Annotated` to the existing `from typing import` line:

```python
from typing import Annotated, Literal
```

Add `Field` to the existing pydantic import:

```python
from pydantic import BaseModel, ConfigDict, Field
```

Append below `AdvisorySet`:

```python
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
```

Update the `__all__` list at the top of models.py (alphabetical):

```python
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
]
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_models.py -v`

Expected: all tests pass.

- [ ] **Step 5: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/models.py tests/test_plugins_models.py
.venv/Scripts/pyright src/nexus/plugins/models.py tests/test_plugins_models.py
```

Both: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/models.py tests/test_plugins_models.py
git commit -m "feat(plugins): add ReverseDependency, ScopeRecordCount, PluginImpact models

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: PluginImpactError

**Files:**
- Modify: `src/nexus/plugins/errors.py`
- Create: `tests/test_plugins_impact.py`

- [ ] **Step 1: Create `tests/test_plugins_impact.py` with file header and first failing test**

```python
# tests/test_plugins_impact.py
# Tests for the plugin impact analysis layer.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for src/nexus/plugins/impact.py and PluginImpactError."""

from nexus.plugins.errors import PluginImpactError

__all__: list[str] = []


def test_plugin_impact_error_carries_plugin_id() -> None:
    err = PluginImpactError("com.unknown")
    assert err.plugin_id == "com.unknown"
    assert "com.unknown" in str(err)


def test_plugin_impact_error_is_exception_subclass() -> None:
    assert issubclass(PluginImpactError, Exception)
```

- [ ] **Step 2: Run; expect FAIL with ImportError**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py -v`

- [ ] **Step 3: Add PluginImpactError to `src/nexus/plugins/errors.py`**

Append:

```python
class PluginImpactError(Exception):
    """Raised when the impact target is not in the captured inventory.

    Args:
        plugin_id: The unknown plugin identifier.
    """

    def __init__(self, plugin_id: str) -> None:
        """Store the unknown plugin id."""
        super().__init__(f"plugin not found in inventory: {plugin_id}")
        self.plugin_id = plugin_id
```

Update `__all__` (alphabetical):

```python
__all__ = ["PluginAdvisoryDataError", "PluginImpactError", "PluginScanError"]
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py -v`

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/plugins/errors.py tests/test_plugins_impact.py
.venv/Scripts/pyright src/nexus/plugins/errors.py tests/test_plugins_impact.py
```

```bash
git add src/nexus/plugins/errors.py tests/test_plugins_impact.py
git commit -m "feat(plugins): add PluginImpactError

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: reverse_dependencies pure graph walk

**Files:**
- Create: `src/nexus/plugins/impact.py`
- Modify: `tests/test_plugins_impact.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_impact.py`:

```python
from datetime import UTC, datetime

import pytest

from nexus.plugins.impact import reverse_dependencies
from nexus.plugins.models import PluginInfo, PluginInventory


def _plugin(
    plugin_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    state: str = "active",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": "1.0",
            "state": state,
            "source": "store",
            "product_family": "Uncategorized",
            "depends_on": depends_on,
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime(2026, 5, 12, tzinfo=UTC),
        sn_version="Washington",
        plugins=plugins,
    )


def test_reverse_dependencies_returns_empty_when_no_dependents() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.unrelated", depends_on=("com.other",)),
    )
    assert reverse_dependencies(inv, "com.target") == ()


def test_reverse_dependencies_finds_direct_dependents_at_depth_1() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.dependent", depends_on=("com.target",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    assert len(deps) == 1
    assert deps[0].plugin_id == "com.dependent"
    assert deps[0].depth == 1


def test_reverse_dependencies_traverses_transitively() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.mid", depends_on=("com.target",)),
        _plugin("com.outer", depends_on=("com.mid",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    ids_by_depth = {d.plugin_id: d.depth for d in deps}
    assert ids_by_depth == {"com.mid": 1, "com.outer": 2}


def test_reverse_dependencies_sets_via_chain_inclusive_of_endpoints() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.mid", depends_on=("com.target",)),
        _plugin("com.outer", depends_on=("com.mid",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    outer = next(d for d in deps if d.plugin_id == "com.outer")
    assert outer.via == ("com.outer", "com.mid", "com.target")


def test_reverse_dependencies_handles_cycles_without_infinite_loop() -> None:
    inv = _inventory(
        _plugin("com.target", depends_on=("com.cycle",)),
        _plugin("com.cycle", depends_on=("com.target",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    assert len(deps) == 1
    assert deps[0].plugin_id == "com.cycle"


def test_reverse_dependencies_handles_self_dependency_without_loop() -> None:
    inv = _inventory(
        _plugin("com.target", depends_on=("com.target",)),
    )
    assert reverse_dependencies(inv, "com.target") == ()


def test_reverse_dependencies_sorts_by_depth_then_plugin_id() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.b", depends_on=("com.target",)),
        _plugin("com.a", depends_on=("com.target",)),
        _plugin("com.deep", depends_on=("com.a",)),
    )
    deps = reverse_dependencies(inv, "com.target")
    order = [(d.depth, d.plugin_id) for d in deps]
    assert order == sorted(order)


def test_reverse_dependencies_raises_when_target_not_in_inventory() -> None:
    inv = _inventory(_plugin("com.other"))
    with pytest.raises(Exception) as info:
        reverse_dependencies(inv, "com.target")
    from nexus.plugins.errors import PluginImpactError

    assert isinstance(info.value, PluginImpactError)
```

- [ ] **Step 2: Run; expect FAIL on import**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py -v -k "reverse_dependencies"`

- [ ] **Step 3: Create `src/nexus/plugins/impact.py`**

```python
# src/nexus/plugins/impact.py
# Plugin impact analysis: reverse-dep graph walk + scope record counts.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Plugin impact analysis layer.

Two-phase design:
    - ``reverse_dependencies`` -- pure BFS over the inventory.
    - ``fetch_scope_record_counts`` -- async aggregate API call.
    - ``compute_impact`` -- async orchestrator.
"""

from __future__ import annotations

from collections import deque

from nexus.plugins.errors import PluginImpactError
from nexus.plugins.models import (
    PluginInventory,
    ReverseDependency,
)

__all__ = ["reverse_dependencies"]


def reverse_dependencies(
    inventory: PluginInventory,
    target: str,
) -> tuple[ReverseDependency, ...]:
    """Walk the reverse dependency graph from ``target``.

    Builds a reverse adjacency map once: ``dependency_id -> set of
    plugin_ids that depend on it``. Then BFS from the target, tracking
    depth and the chain of plugin_ids that lead back to the target.
    A visited set keyed by ``plugin_id`` guards against cycles.

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
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py -v -k "reverse_dependencies"`

Expected: 8 PASS.

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/plugins/impact.py tests/test_plugins_impact.py
.venv/Scripts/pyright src/nexus/plugins/impact.py tests/test_plugins_impact.py
```

```bash
git add src/nexus/plugins/impact.py tests/test_plugins_impact.py
git commit -m "feat(plugins): add reverse_dependencies graph walk

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: fetch_scope_record_counts async REST fetcher

**Files:**
- Modify: `src/nexus/plugins/impact.py`
- Modify: `tests/test_plugins_impact.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_impact.py`:

```python
import asyncio

import httpx

from nexus.plugins.impact import (
    ScopeRecordCountError,
    fetch_scope_record_counts,
)


def _stats_response(rows: list[dict[str, object]]) -> dict[str, object]:
    return {"result": rows}


def _row(table: str, count: int) -> dict[str, object]:
    return {
        "stats": {"count": str(count)},
        "groupby_fields": [{"field": "sys_class_name", "value": table}],
    }


def _stats_transport(
    status: int = 200,
    payload: dict[str, object] | None = None,
) -> httpx.MockTransport:
    body = payload if payload is not None else {"result": []}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


def _fetch(transport: httpx.MockTransport) -> tuple:
    return asyncio.run(
        fetch_scope_record_counts(
            "https://x.example",
            "tok",
            "com.target",
            transport=transport,
        )
    )


def test_fetch_scope_record_counts_parses_aggregate_response() -> None:
    transport = _stats_transport(
        payload=_stats_response([_row("sys_script", 8012)]),
    )
    counts = _fetch(transport)
    assert len(counts) == 1
    assert counts[0].table == "sys_script"
    assert counts[0].count == 8012


def test_fetch_scope_record_counts_returns_empty_tuple_when_result_empty() -> None:
    transport = _stats_transport(payload=_stats_response([]))
    assert _fetch(transport) == ()


def test_fetch_scope_record_counts_sorts_by_count_desc_then_table_asc() -> None:
    transport = _stats_transport(
        payload=_stats_response(
            [
                _row("sys_business_rule", 100),
                _row("sys_script", 500),
                _row("sys_ui_action", 500),
            ]
        ),
    )
    counts = _fetch(transport)
    assert [(c.table, c.count) for c in counts] == [
        ("sys_script", 500),
        ("sys_ui_action", 500),
        ("sys_business_rule", 100),
    ]


def test_fetch_scope_record_counts_raises_on_non_200() -> None:
    transport = _stats_transport(status=403)
    with pytest.raises(ScopeRecordCountError):
        _fetch(transport)


def test_fetch_scope_record_counts_raises_on_malformed_response() -> None:
    transport = _stats_transport(payload={"no_result_key": True})
    with pytest.raises(ScopeRecordCountError):
        _fetch(transport)
```

- [ ] **Step 2: Run; expect FAIL on imports**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py -v -k "fetch_scope_record_counts"`

- [ ] **Step 3: Add `fetch_scope_record_counts` + `ScopeRecordCountError` to `src/nexus/plugins/impact.py`**

Add these imports (merge with existing):

```python
import logging

import httpx

from nexus.plugins.models import ScopeRecordCount
```

Add `log` near the top:

```python
log = logging.getLogger(__name__)
```

Append:

```python
class ScopeRecordCountError(Exception):
    """Raised when the live aggregate REST call fails or is unparseable.

    Internal to ``impact.py``; not surfaced at the public ``nexus.plugins``
    layer. ``compute_impact`` catches it to set ``counts_available=False``.
    """


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
    params = {
        "sysparm_query": f"sys_scope.scope={plugin_id}",
        "sysparm_count": "true",
        "sysparm_group_by": "sys_class_name",
    }
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            base_url=url,
            headers=headers,
            timeout=30.0,
            transport=transport,
        ) as client:
            response = await client.get("/api/now/stats/sys_metadata", params=params)
    except httpx.RequestError as exc:
        raise ScopeRecordCountError(f"network error: {exc}") from exc

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
                entry["value"] for entry in groupby if entry.get("field") == "sys_class_name"
            )
        except (KeyError, StopIteration, TypeError, ValueError) as exc:
            raise ScopeRecordCountError(f"malformed row: {exc}") from exc
        counts.append(ScopeRecordCount(table=table, count=count))

    counts.sort(key=lambda c: (-c.count, c.table))
    return tuple(counts)
```

Extend `__all__`:

```python
__all__ = [
    "ScopeRecordCountError",
    "fetch_scope_record_counts",
    "reverse_dependencies",
]
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py -v -k "fetch_scope_record_counts"`

Expected: 5 PASS.

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/plugins/impact.py tests/test_plugins_impact.py
.venv/Scripts/pyright src/nexus/plugins/impact.py tests/test_plugins_impact.py
```

```bash
git add src/nexus/plugins/impact.py tests/test_plugins_impact.py
git commit -m "feat(plugins): add fetch_scope_record_counts via Aggregate API

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: compute_impact orchestrator

**Files:**
- Modify: `src/nexus/plugins/impact.py`
- Modify: `tests/test_plugins_impact.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_impact.py`:

```python
from nexus.plugins.impact import compute_impact
from nexus.plugins.models import PluginImpact


def test_compute_impact_aggregates_reverse_deps_and_counts() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.dependent", depends_on=("com.target",)),
    )
    transport = _stats_transport(
        payload=_stats_response([_row("sys_script", 42)]),
    )
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="tok",
            transport=transport,
        )
    )
    assert isinstance(result, PluginImpact)
    assert result.counts_available is True
    assert result.target_plugin_id == "com.target"
    assert len(result.reverse_deps) == 1
    assert len(result.record_counts) == 1
    assert result.record_counts[0].count == 42


def test_compute_impact_marks_counts_unavailable_when_fetch_fails() -> None:
    inv = _inventory(
        _plugin("com.target"),
        _plugin("com.dependent", depends_on=("com.target",)),
    )
    transport = _stats_transport(status=500)
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="tok",
            transport=transport,
        )
    )
    assert result.counts_available is False
    assert result.record_counts == ()
    assert len(result.reverse_deps) == 1


def test_compute_impact_propagates_plugin_not_found() -> None:
    inv = _inventory(_plugin("com.other"))
    transport = _stats_transport()
    with pytest.raises(PluginImpactError):
        asyncio.run(
            compute_impact(
                inv,
                "com.target",
                url="https://x.example",
                token="tok",
                transport=transport,
            )
        )
```

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py -v -k "compute_impact"`

- [ ] **Step 3: Add compute_impact to `src/nexus/plugins/impact.py`**

Add to imports (merge with existing `from nexus.plugins.models import ...`):

```python
from nexus.plugins.models import PluginImpact, PluginInventory, ReverseDependency, ScopeRecordCount
```

Append:

```python
async def compute_impact(
    inventory: PluginInventory,
    target: str,
    *,
    url: str,
    token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PluginImpact:
    """Join the graph walk and the live aggregate call.

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
```

Extend `__all__`:

```python
__all__ = [
    "ScopeRecordCountError",
    "compute_impact",
    "fetch_scope_record_counts",
    "reverse_dependencies",
]
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py -v`

Expected: 16 PASS (8 + 5 + 3).

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/plugins/impact.py tests/test_plugins_impact.py
.venv/Scripts/pyright src/nexus/plugins/impact.py tests/test_plugins_impact.py
```

```bash
git add src/nexus/plugins/impact.py tests/test_plugins_impact.py
git commit -m "feat(plugins): add compute_impact orchestrator

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Public re-exports

**Files:**
- Modify: `src/nexus/plugins/__init__.py`
- Modify: `tests/test_plugins_impact.py`

- [ ] **Step 1: Append failing test**

```python
def test_public_api_reexports_impact_symbols() -> None:
    import nexus.plugins as pkg

    expected = {
        "PluginImpact",
        "PluginImpactError",
        "ReverseDependency",
        "ScopeRecordCount",
        "compute_impact",
        "reverse_dependencies",
    }
    assert expected.issubset(set(pkg.__all__))
    for name in expected:
        assert hasattr(pkg, name), f"missing re-export: {name}"
```

NOTE: The plan's `import nexus.plugins as pkg` line must live at module-top per ruff PLC0415, not inside the function body. The above shows it inside the function for readability of the spec; the implementer should hoist it to the existing top-of-file `import` block (sub-project D1 did the same).

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py::test_public_api_reexports_impact_symbols -v`

- [ ] **Step 3: Update `src/nexus/plugins/__init__.py`**

Replace the entire file contents (preserve the existing 4-line header):

```python
# src/nexus/plugins/__init__.py
# Public re-exports for the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""nexus.plugins: read-only plugin inventory layer.

Exports the data models, scanner, error types, product-family lookup,
the cross-instance diff/promote helpers, the update-detection filter,
the advisory checkers (EOL, CVE, license), and the impact analyzer
(reverse-dep graph + scope record counts).
"""

from nexus.plugins.advisories import AdvisoryDatabase, compute_advisories
from nexus.plugins.diff import (
    PluginDiff,
    PluginDiffEntry,
    PromoteAction,
    PromotionPlan,
    compute_diff,
    project_to_promote_plan,
)
from nexus.plugins.errors import (
    PluginAdvisoryDataError,
    PluginImpactError,
    PluginScanError,
)
from nexus.plugins.impact import compute_impact, reverse_dependencies
from nexus.plugins.models import (
    AdvisoryFinding,
    AdvisorySet,
    AdvisoryType,
    PluginImpact,
    PluginInfo,
    PluginInventory,
    ProductFamily,
    ReverseDependency,
    ScopeRecordCount,
    Severity,
)
from nexus.plugins.product_families import product_family_for
from nexus.plugins.scanner import PluginScanner
from nexus.plugins.updates import plugins_with_updates

__all__ = [
    "AdvisoryDatabase",
    "AdvisoryFinding",
    "AdvisorySet",
    "AdvisoryType",
    "PluginAdvisoryDataError",
    "PluginDiff",
    "PluginDiffEntry",
    "PluginImpact",
    "PluginImpactError",
    "PluginInfo",
    "PluginInventory",
    "PluginScanError",
    "PluginScanner",
    "ProductFamily",
    "PromoteAction",
    "PromotionPlan",
    "ReverseDependency",
    "ScopeRecordCount",
    "Severity",
    "compute_advisories",
    "compute_diff",
    "compute_impact",
    "plugins_with_updates",
    "product_family_for",
    "project_to_promote_plan",
    "reverse_dependencies",
]
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py::test_public_api_reexports_impact_symbols -v`

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/plugins/__init__.py tests/test_plugins_impact.py
.venv/Scripts/pyright src/nexus/plugins/__init__.py tests/test_plugins_impact.py
```

```bash
git add src/nexus/plugins/__init__.py tests/test_plugins_impact.py
git commit -m "feat(plugins): expose impact analysis layer

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: CLI `nexus plugins impact` command

**Files:**
- Modify: `src/nexus/cli.py`
- Create: `tests/test_cli_plugins_impact.py`

- [ ] **Step 1: Inspect existing CLI helpers**

Read these before editing:
- `src/nexus/cli.py:104-117` -- plugins_app declaration + _PLUGINS_HELP list (add an entry).
- `src/nexus/cli.py:630` -- `_acquire_token(profile) -> (registry, meta, token, expiry)` helper.
- `src/nexus/cli.py:1387` -- the existing `plugins_updates` command (the closest shape to model from).
- `_load_inventory_or_exit(profile)` -- already used by updates/diff/advisories.

- [ ] **Step 2: Write failing CLI tests**

Create `tests/test_cli_plugins_impact.py`:

```python
# tests/test_cli_plugins_impact.py
# Tests for the nexus plugins impact command.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus plugins impact."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
from nexus.plugins.impact import ScopeRecordCountError
from nexus.plugins.models import PluginInfo, PluginInventory

__all__: list[str] = []


def _meta(profile: str) -> InstanceMeta:
    return InstanceMeta.create(
        profile=profile,
        url=f"https://{profile}.service-now.com",
        username="admin",
        client_id="cid",
        sn_version="Xanadu",
        sn_build="04-01-2025_1200",
        instance_name=profile,
        token_expires_in=1800,
    )


def _info(
    plugin_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    state: str = "active",
) -> PluginInfo:
    return PluginInfo.model_validate(
        {
            "plugin_id": plugin_id,
            "name": plugin_id,
            "version": "1.0",
            "state": state,
            "source": "store",
            "product_family": "Uncategorized",
            "depends_on": depends_on,
            "sys_id": f"sys-{plugin_id}",
            "installed_at": None,
        }
    )


def _seed(
    tmp_path: Path,
    profile: str,
    plugins: tuple[PluginInfo, ...] | None,
) -> None:
    profile_dir = tmp_path / "instances" / profile
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "meta.json").write_text(
        _meta(profile).model_dump_json(indent=2), encoding="utf-8"
    )
    if plugins is not None:
        inv = PluginInventory(
            captured_at=datetime.now(UTC),
            sn_version="Xanadu",
            plugins=plugins,
        )
        (profile_dir / "plugins.json").write_text(inv.model_dump_json(indent=2), encoding="utf-8")


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def _ok_stats_payload() -> dict[str, object]:
    return {
        "result": [
            {
                "stats": {"count": "42"},
                "groupby_fields": [{"field": "sys_class_name", "value": "sys_script"}],
            }
        ]
    }


def _patch_token_and_stats(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stats_status: int = 200,
    stats_payload: dict[str, object] | None = None,
) -> None:
    """Stub _acquire_token and route Aggregate API through a MockTransport."""
    from nexus.cli import _resolve_profile

    def fake_acquire(profile: str) -> tuple:
        registry, meta = _resolve_profile(profile)
        return registry, meta, "fake-token", datetime.now(UTC)

    monkeypatch.setattr("nexus.cli._acquire_token", fake_acquire)

    payload = stats_payload if stats_payload is not None else _ok_stats_payload()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(stats_status, json=payload)

    monkeypatch.setattr(
        "nexus.cli._impact_transport", lambda: httpx.MockTransport(handler)
    )


def test_impact_renders_reverse_deps_and_counts_tables(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.target"),
            _info("com.dependent", depends_on=("com.target",)),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 0
    assert "Reverse dependencies" in result.output
    assert "com.dependent" in result.output
    assert "sys_script" in result.output
    assert "42" in result.output


def test_impact_prints_no_dependents_message_when_none(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 0
    assert "No plugins depend on com.target" in result.output


def test_impact_warns_when_record_counts_unavailable(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.target"),
            _info("com.dependent", depends_on=("com.target",)),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch, stats_status=500)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 0
    assert "Record counts unavailable" in result.output
    assert "com.dependent" in result.output


def test_impact_errors_when_plugin_not_in_inventory(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.other"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 1
    assert "Plugin not found" in result.output


def test_impact_warns_when_inventory_missing(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", None)
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(app, ["plugins", "impact", "com.target"])
    assert result.exit_code == 1
    assert "nexus instance refresh" in result.output
```

The `_impact_transport` helper in cli.py is a module-level seam that defaults to returning `None` so production code uses the real HTTP transport; tests monkeypatch it to inject a `MockTransport`. This is the same pattern other parts of the codebase use to make async REST tests deterministic.

- [ ] **Step 3: Run; expect FAIL on import/command-missing**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_impact.py -v`

- [ ] **Step 4: Add the impact command to `src/nexus/cli.py`**

Add to the existing `nexus.plugins` imports at the top:

```python
from nexus.plugins.errors import PluginAdvisoryDataError, PluginImpactError
from nexus.plugins.impact import compute_impact
from nexus.plugins.models import (
    AdvisoryFinding,
    AdvisoryType,
    PluginImpact,
    PluginInfo,
    Severity,
)
```

(Merge with existing `from nexus.plugins.errors import ...` and `from nexus.plugins.models import ...` lines -- do not create duplicates.)

Add `asyncio` to the existing import block if not already present:

```python
import asyncio
```

Update `_PLUGINS_HELP` to include the new command (add as the LAST entry):

```python
_PLUGINS_HELP = [
    ("list", "Show all plugins with optional --product / --source / --state filters"),
    ("info <plugin_id>", "Show full details and dependencies for one plugin"),
    ("export", "Write the inventory to YAML or CSV"),
    ("diff <a> <b>", "Show cross-instance plugin differences"),
    ("promote <src> --to <dst>", "Write an action plan to make <dst> match <src>"),
    ("updates", "Show plugins with newer versions available"),
    ("advisories", "Show EOL / CVE / license findings"),
    ("impact <plugin_id>", "Show reverse-deps + scope record counts"),
]
```

Append after the existing `plugins_advisories` command:

```python
def _impact_transport() -> httpx.AsyncBaseTransport | None:
    """Return the async transport used by the impact command.

    In production this returns ``None`` so httpx uses the real network.
    Tests monkeypatch this to inject an ``httpx.MockTransport``.
    """
    return None


@plugins_app.command("impact")
def plugins_impact(
    plugin_id: Annotated[
        str,
        typer.Argument(help="Plugin identifier (e.g. com.acme.helper)"),
    ],
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
) -> None:
    """Show reverse dependencies + scope-owned record counts for a plugin."""
    _, inventory = _load_inventory_or_exit(instance)
    _registry, meta, token, _expiry = _acquire_token(instance)
    transport = _impact_transport()
    try:
        impact = asyncio.run(
            compute_impact(
                inventory,
                plugin_id,
                url=meta.url,
                token=token,
                transport=transport,
            )
        )
    except PluginImpactError as exc:
        console.print(Notice.error(f"Plugin not found: {plugin_id}"))
        raise typer.Exit(1) from exc

    _render_impact(impact)


def _render_impact(impact: PluginImpact) -> None:
    """Render the two impact DataTables + trailing summary Notice.

    Args:
        impact: PluginImpact from compute_impact.
    """
    if impact.reverse_deps:
        rows: list[list[RenderableType]] = [
            [
                d.plugin_id,
                d.name,
                d.state,
                str(d.depth),
                _trunc("->".join(d.via), 60),
            ]
            for d in impact.reverse_deps
        ]
        console.print(
            DataTable(
                title="Reverse dependencies",
                columns=[
                    DataColumn(header="Plugin ID", width=32),
                    DataColumn(header="Name", width=20),
                    DataColumn(header="State", width=10),
                    DataColumn(header="Depth", width=7),
                    DataColumn(header="Via", width=60),
                ],
                rows=rows,
            )
        )
    else:
        console.print(Notice.info(f"No plugins depend on {impact.target_plugin_id}."))

    total_records = 0
    if not impact.counts_available:
        console.print(
            Notice.warn("Record counts unavailable -- could not reach instance.")
        )
    elif not impact.record_counts:
        console.print(Notice.info("No scope-owned records."))
    else:
        count_rows: list[list[RenderableType]] = [
            [c.table, f"{c.count:,}"] for c in impact.record_counts
        ]
        console.print(
            DataTable(
                title="Scope-owned records",
                columns=[
                    DataColumn(header="Table", width=32),
                    DataColumn(header="Count", width=12),
                ],
                rows=count_rows,
            )
        )
        total_records = sum(c.count for c in impact.record_counts)

    if impact.counts_available:
        console.print(
            Notice.info(
                f"{len(impact.reverse_deps)} dependent plugin(s); "
                f"{total_records:,} records in scope {impact.target_plugin_id}."
            )
        )
    else:
        console.print(
            Notice.info(
                f"{len(impact.reverse_deps)} dependent plugin(s)."
            )
        )
```

Verify `httpx`, `asyncio`, `RenderableType` are already imported at the top of cli.py (they are -- httpx and RenderableType are used elsewhere; asyncio may need adding).

- [ ] **Step 5: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_impact.py -v`

Expected: 5 PASS.

- [ ] **Step 6: Smoke-render help**

`.venv/Scripts/nexus plugins impact --help`

Expected: help text shows `<plugin_id>` positional and `--instance` option.

- [ ] **Step 7: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/cli.py tests/test_cli_plugins_impact.py
.venv/Scripts/pyright src/nexus/cli.py tests/test_cli_plugins_impact.py
```

```bash
git add src/nexus/cli.py tests/test_cli_plugins_impact.py
git commit -m "feat(cli): add nexus plugins impact command

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Black + ratchet refresh + PR

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Black**

`.venv/Scripts/black src/nexus/plugins/ src/nexus/cli.py tests/test_plugins_impact.py tests/test_cli_plugins_impact.py tests/test_plugins_models.py`

- [ ] **Step 2: Full quality gate**

```
.venv/Scripts/ruff check src tests        # 0 violations
.venv/Scripts/mypy src/nexus/             # 0 errors
.venv/Scripts/pyright src/nexus/          # 0 errors
.venv/Scripts/python -m pytest --no-cov --ignore=tests/test_updater_runner.py
# Expected: all new tests pass; 4 pre-existing failures unchanged
```

- [ ] **Step 3: Measure coverage**

```
.venv/Scripts/python -m pytest --ignore=tests/test_updater_runner.py --cov=nexus --cov-report=json --cov-fail-under=0
```

Extract numbers for:
- `src/nexus/cli.py`
- `src/nexus/plugins/__init__.py`
- `src/nexus/plugins/errors.py`
- `src/nexus/plugins/impact.py`
- `src/nexus/plugins/models.py`

- [ ] **Step 4: Update `.ratchet.json`**

Update or insert the following keys with the freshly measured values. Do not change unrelated keys.

```jsonc
{
  ...
  "modules": {
    ...
    "nexus.cli": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.__init__": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.errors": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.impact": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.models": {"covered_lines": <new>, "total_lines": <new>},
    ...
  }
}
```

Ratchet rule: `covered_lines` must be >= the previous value for each module; `total_lines` reflects the new module size.

If `coverage.json` is tracked in the repo (it has been historically), restore it after measurement: `git checkout coverage.json`.

- [ ] **Step 5: Commit**

```bash
git add .ratchet.json src/nexus/plugins/ src/nexus/cli.py tests/
git commit -m "chore(plugins): black formatting + refresh ratchet for impact layer

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Push + open PR**

```bash
git push -u origin feat/plugins-impact
gh pr create --base feat/plugins-advisories --title "feat(plugins): D2 impact analysis (reverse-deps + record counts)" --body "$(cat <<'EOF'
## Summary
- `nexus plugins impact <plugin_id>` shows the transitive reverse-dependency closure of a plugin and per-table record counts in its scope.
- Reverse-deps derived from the cached inventory (pure BFS, no extra REST calls).
- Record counts via one live Aggregate API call to `/api/now/stats/sys_metadata`. Graceful degradation: REST failure marks counts unavailable; reverse-deps still ship.
- Adds `nexus.plugins.impact` module + `ReverseDependency`/`ScopeRecordCount`/`PluginImpact` models + `PluginImpactError` exception.

Sub-project D2 of plugin management. Stacked on PR #14 (`feat/plugins-advisories`).

Spec: docs/superpowers/specs/2026-05-12-plugin-impact-design.md

## Test plan
- [x] `pytest tests/test_plugins_impact.py -v` (16 unit tests)
- [x] `pytest tests/test_cli_plugins_impact.py -v` (5 CLI tests)
- [x] `pytest` full suite green except 4 pre-existing failures
- [x] ruff / black / mypy / pyright clean
- [x] `nexus plugins impact --help` smoke render

EOF
)"
```

---

## Self-Review Summary

**Spec coverage:**
- ReverseDependency / ScopeRecordCount / PluginImpact models -> Task 1
- PluginImpactError -> Task 2
- reverse_dependencies pure BFS with cycle handling + via chain + sort -> Task 3
- fetch_scope_record_counts async Aggregate API call -> Task 4
- compute_impact orchestrator with graceful degradation -> Task 5
- Public re-exports -> Task 6
- CLI command with empty-deps message, counts-unavailable warning, plugin-not-found error path -> Task 7
- Black, quality gate, ratchet refresh, PR -> Task 8

All spec sections traced to a task. No gaps.

**Placeholder scan:** No "TBD" / "TODO" / "etc." in the plan body. Each step contains concrete code or a concrete command. The `<new>` placeholders in the ratchet update are intentionally pinned to "measure then fill in" -- explicit instruction.

**Type consistency:** All signatures consistent across tasks. `reverse_dependencies(inventory, target) -> tuple[ReverseDependency, ...]` matches usage in Task 5. `fetch_scope_record_counts(url, token, plugin_id, *, transport) -> tuple[ScopeRecordCount, ...]` matches usage in Task 5. `compute_impact(inventory, target, *, url, token, transport) -> PluginImpact` matches usage in Task 7. `PluginImpact` fields consistent throughout. `ScopeRecordCountError` is the private exception name used in both Task 4 (where it's defined) and Task 5 (where compute_impact catches it).
