# Plugin Inventory Refinements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the per-table record-count breakdown that the scanner already computes (was scalar `record_count`, becomes `record_counts: tuple[ScopeRecordCount, ...]`), replace fragile partial-page-break pagination with RFC 5988 Link-header walking, and invalidate legacy on-disk inventories with a refresh hint.

**Architecture:** Atomic refactor of `PluginInfo` propagated through five consumer modules (`scanner.py`, `orphans.py`, `impact.py`, `cli.py`, `registry.py`). Ordering uses a transient dual-write so the suite stays green at every commit boundary: add the new field, dual-write in scanner, switch consumers, drop the old field. Pagination change and registry invalidation are independent commits.

**Tech Stack:** Python 3.14+, Pydantic v2 (`frozen=True, strict=True, extra="forbid"`), httpx + httpx.MockTransport for scanner tests, typer.testing.CliRunner for CLI tests.

**Branch:** `feat/plugins-inventory-refinements` (already checked out at SHA `305a7ff`, branched from `main` at `5fae099`).

**Spec:** [docs/superpowers/specs/2026-05-12-plugin-inventory-refinements-design.md](../specs/2026-05-12-plugin-inventory-refinements-design.md)

---

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `src/nexus/plugins/models.py` | Add `record_counts` field + `total_records` helper; drop `record_count` field at the end. | 1, 6 |
| `src/nexus/plugins/scanner.py` | Dual-write record_count + record_counts; then single-write record_counts; switch `_fetch` to Link-header pagination. | 2, 6, 8 |
| `src/nexus/plugins/orphans.py` | Filter via `total_records(p) == 0`. | 3 |
| `src/nexus/plugins/impact.py` | Cache-first fast-path; add `live: bool = False` param. | 4 |
| `src/nexus/cli.py` | `--live` flag on `plugins impact`; orphans precheck reads `record_counts`. | 5 |
| `src/nexus/instances/registry.py` | Wrap inventory + baseline loads in try/except `ValidationError`; return None + warn on legacy shape. | 7 |
| `tests/test_plugins_models.py` | Helper + field tests. | 1, 6 |
| `tests/test_plugins_scanner.py` | Dual-shape -> single-shape; Link-header pagination tests. | 2, 6, 8 |
| `tests/test_plugins_orphans.py` | Fixtures switch from `record_count` to `record_counts`. | 3 |
| `tests/test_plugins_impact.py` | Cache-serve + `--live` flag tests. | 4 |
| `tests/test_cli_plugins_impact.py` | `--live` CLI flag tests. | 5 |
| `tests/test_cli_plugins_orphans.py` | Precheck-warning fixture update. | 5 |
| `tests/test_instances_registry.py` | Legacy-shape invalidation tests. | 7 |
| `.ratchet.json` | Per-module covered_lines bump after green run. | 9 |

---

## Task 1: Add `record_counts` field + `total_records` helper (additive)

**Files:**
- Modify: `src/nexus/plugins/models.py`
- Modify: `tests/test_plugins_models.py`

This task is purely additive: existing `record_count` field stays. Adds the new tuple-shaped field defaulting to `None` and a module-level `total_records` helper. After this task the suite remains 100% green.

- [ ] **Step 1: Write failing tests for `total_records` and the new field default**

Add to `tests/test_plugins_models.py` (append below the existing tests):

```python
def test_total_records_with_none_returns_none() -> None:
    from nexus.plugins.models import total_records

    info = _info()
    assert info.record_counts is None
    assert total_records(info) is None


def test_total_records_with_empty_tuple_returns_zero() -> None:
    from nexus.plugins.models import total_records

    info = _info(record_counts=())
    assert total_records(info) == 0


def test_total_records_with_single_bucket_returns_count() -> None:
    from nexus.plugins.models import total_records

    info = _info(record_counts=(ScopeRecordCount(table="sys_script", count=42),))
    assert total_records(info) == 42


def test_total_records_with_multi_bucket_returns_sum() -> None:
    from nexus.plugins.models import total_records

    info = _info(
        record_counts=(
            ScopeRecordCount(table="sys_script", count=100),
            ScopeRecordCount(table="sys_business_rule", count=25),
        )
    )
    assert total_records(info) == 125


def test_plugin_info_record_counts_defaults_to_none() -> None:
    info = _info()
    assert info.record_counts is None


def test_plugin_info_accepts_record_counts_tuple() -> None:
    info = _info(record_counts=(ScopeRecordCount(table="sys_script", count=7),))
    assert len(info.record_counts) == 1
    assert info.record_counts[0].count == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_models.py -v -k "total_records or record_counts"`

Expected: 6 FAILs. The first four fail with `ImportError` (helper not defined). The two `record_counts` field tests fail with Pydantic `ValidationError: extra="forbid"` because the field does not exist yet.

- [ ] **Step 3: Add the new field and helper to `src/nexus/plugins/models.py`**

Update the `PluginInfo` class to add the field. In `src/nexus/plugins/models.py`, replace lines 84-85 (the `record_count: int | None = None` line and the surrounding lines) so the field set reads:

```python
    latest_version: str | None = None
    vendor: str = ""
    record_count: int | None = None
    record_counts: tuple[ScopeRecordCount, ...] | None = None
```

Update the `record_count` docstring entry already present in the class docstring, and add a `record_counts` entry next to it:

```python
        record_count: Total records in this plugin's scope as reported by
            ``sys_metadata`` aggregation. ``None`` when not captured (older
            snapshots, or a partial-fetch failure during scan). Used by
            orphan detection. Deprecated -- being replaced by
            ``record_counts``; will be removed in this sub-project.
        record_counts: Per-table record counts owned by this plugin's
            scope, sorted by ``(count desc, table asc)``. ``None`` when
            uncaptured. Empty tuple means the scope owns zero records.
```

Append the helper at the bottom of the module (after `PluginImpact`):

```python
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
```

Update `__all__` (top of file, around line 14) to add `"total_records"` in alphabetical order with the other public names. Final list:

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
    "total_records",
]
```

- [ ] **Step 4: Run all model tests to verify they pass**

Run: `pytest tests/test_plugins_models.py -v`

Expected: all tests PASS (existing + 6 new = previous count + 6).

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `pytest -q`

Expected: all tests PASS (existing total + 6 new).

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/models.py tests/test_plugins_models.py
git commit -m "$(cat <<'EOF'
feat(plugins): add record_counts field and total_records helper

Additive change toward sub-project I: PluginInfo gains a per-table
record-count tuple field alongside the existing record_count scalar.
total_records() sums the tuple (None when uncaptured, 0 when empty).
Consumers still read record_count; field shift completes in later tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Scanner dual-writes `record_count` and `record_counts`

**Files:**
- Modify: `src/nexus/plugins/scanner.py`
- Modify: `tests/test_plugins_scanner.py`

Replace `_sum_scope_records` and the `_ScopeRecordCountError` shim. `_fetch_counts` now returns the breakdown directly. `scan()` populates both fields. Existing consumers continue to read `record_count` (unchanged behavior); `record_counts` is new and currently unread.

- [ ] **Step 1: Write the failing test for record_counts persistence**

Add to `tests/test_plugins_scanner.py` (append after `test_scan_keeps_other_fields_intact_after_count_capture`):

```python
def test_scan_populates_record_counts_breakdown() -> None:
    transport = _transport_for(
        stats_payload=_stats_response(
            [
                _stats_row("sys_script", 100),
                _stats_row("sys_business_rule", 25),
            ]
        ),
    )
    inv = asyncio.run(_scan(transport))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.record_counts is not None
    counts_by_table = {c.table: c.count for c in incident.record_counts}
    assert counts_by_table == {"sys_script": 100, "sys_business_rule": 25}


def test_scan_sets_record_counts_none_when_aggregate_call_fails() -> None:
    transport = _transport_for(stats_status=500)
    inv = asyncio.run(_scan(transport))
    assert all(p.record_counts is None for p in inv.plugins)


def test_scan_populates_record_counts_empty_tuple_when_scope_has_zero_records() -> None:
    transport = _transport_for(stats_payload=_stats_response([]))
    inv = asyncio.run(_scan(transport))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.record_counts == ()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_scanner.py::test_scan_populates_record_counts_breakdown tests/test_plugins_scanner.py::test_scan_sets_record_counts_none_when_aggregate_call_fails tests/test_plugins_scanner.py::test_scan_populates_record_counts_empty_tuple_when_scope_has_zero_records -v`

Expected: 3 FAILs. All `record_counts` reads return `None` because the scanner does not populate it yet.

- [ ] **Step 3: Refactor `scanner.py` — remove sum-shim, return breakdown**

In `src/nexus/plugins/scanner.py`:

1. Remove the now-unused imports of `_ImpactScopeRecordCountError` and `_fetch_scope_counts_with_client` aliases at the top — replace:

```python
from nexus.plugins.impact import (
    ScopeRecordCountError as _ImpactScopeRecordCountError,
)
from nexus.plugins.impact import (
    fetch_scope_counts_with_client as _fetch_scope_counts_with_client,
)
```

with:

```python
from nexus.plugins.impact import ScopeRecordCountError, fetch_scope_counts_with_client
```

2. Delete the `_ScopeRecordCountError` class (lines 241-247) and the `_sum_scope_records` function (lines 250-270) entirely.

3. Replace `_fetch_counts` (lines 276-306) with the breakdown-returning version:

```python
async def _fetch_counts(
    client: httpx.AsyncClient,
    plugin_ids: tuple[str, ...],
    *,
    max_concurrency: int = _DEFAULT_COUNTS_CONCURRENCY,
) -> dict[str, tuple[ScopeRecordCount, ...] | None]:
    """Fan out aggregate-API calls and return per-table breakdowns.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        plugin_ids: Plugins to fetch counts for.
        max_concurrency: Maximum number of in-flight stats calls.

    Returns:
        ``plugin_id -> tuple of ScopeRecordCount`` mapping. Per-plugin
        failures surface as ``None`` so the whole refresh can succeed
        with partial data.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _one(pid: str) -> tuple[str, tuple[ScopeRecordCount, ...] | None]:
        async with semaphore:
            try:
                buckets = await fetch_scope_counts_with_client(client, pid)
            except ScopeRecordCountError as exc:
                log.warning("scan: count fetch failed for %s -- %s", pid, exc)
                return pid, None
            return pid, buckets

    results = await asyncio.gather(*(_one(pid) for pid in plugin_ids))
    return dict(results)
```

4. Add the `ScopeRecordCount` import to scanner.py (top imports). Final top-of-file imports look like:

```python
from nexus.plugins.errors import PluginScanError
from nexus.plugins.impact import ScopeRecordCountError, fetch_scope_counts_with_client
from nexus.plugins.models import PluginInfo, PluginInventory, ScopeRecordCount
from nexus.plugins.product_families import product_family_for
```

5. Add a local helper just below `_fetch_counts`:

```python
def _total_or_none(buckets: tuple[ScopeRecordCount, ...] | None) -> int | None:
    """Sum a breakdown tuple or pass through ``None``."""
    if buckets is None:
        return None
    return sum(b.count for b in buckets)
```

6. Update `scan()` body to dual-write. Replace the existing `if capture_counts:` block (lines 105-110):

```python
            if capture_counts:
                breakdown = await _fetch_counts(client, tuple(by_id.keys()))
                by_id = {
                    pid: info.model_copy(
                        update={
                            "record_count": _total_or_none(breakdown.get(pid)),
                            "record_counts": breakdown.get(pid),
                        }
                    )
                    for pid, info in by_id.items()
                }
```

- [ ] **Step 4: Update existing scanner tests that referenced removed helpers**

In `tests/test_plugins_scanner.py`, remove the now-broken imports and tests:

1. Remove from the import block (lines 14-20):

```python
from nexus.plugins.scanner import (
    PluginScanner,
    _fetch_counts,
    _ScopeRecordCountError,
    _sum_scope_records,
)
```

Replace with:

```python
from nexus.plugins.scanner import PluginScanner, _fetch_counts
```

2. Delete these four tests entirely (lines 198-226):
   - `test_sum_scope_records_returns_total_across_tables`
   - `test_sum_scope_records_returns_zero_for_empty_result`
   - `test_sum_scope_records_raises_on_non_200`
   - `test_sum_scope_records_raises_on_malformed_response`
   - Also delete the `_run_sum` helper (lines 189-195).

3. Update `test_fetch_counts_returns_count_per_plugin` and `test_fetch_counts_marks_failed_plugin_as_none` to assert against the new return type. Replace both tests:

```python
def test_fetch_counts_returns_breakdown_per_plugin() -> None:
    transport = _transport_for(
        stats_payload=_stats_response([_stats_row("sys_script", 7)]),
    )

    async def _run() -> dict[str, tuple[object, ...] | None]:
        async with httpx.AsyncClient(
            base_url="https://x.example",
            headers={"Authorization": "Bearer t"},
            transport=transport,
        ) as client:
            return await _fetch_counts(client, ("com.a", "com.b"))

    counts = asyncio.run(_run())
    assert set(counts.keys()) == {"com.a", "com.b"}
    a_buckets = counts["com.a"]
    assert a_buckets is not None
    assert len(a_buckets) == 1
    assert a_buckets[0].table == "sys_script"
    assert a_buckets[0].count == 7


def test_fetch_counts_marks_failed_plugin_as_none() -> None:
    transport = _transport_for(stats_status=500)

    async def _run() -> dict[str, tuple[object, ...] | None]:
        async with httpx.AsyncClient(
            base_url="https://x.example",
            headers={"Authorization": "Bearer t"},
            transport=transport,
        ) as client:
            return await _fetch_counts(client, ("com.a", "com.b"))

    counts = asyncio.run(_run())
    assert counts == {"com.a": None, "com.b": None}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_plugins_scanner.py -v`

Expected: all tests PASS. The 4 deleted `_sum_scope_records` tests no longer run; the 2 modified `_fetch_counts` tests verify the new shape; the 3 new `record_counts` tests pass.

- [ ] **Step 6: Run the full suite to confirm dual-write keeps consumers green**

Run: `pytest -q`

Expected: all tests PASS. `record_count` is still populated by the scanner via `_total_or_none`, so orphans, impact, and cli precheck still work.

- [ ] **Step 7: Commit**

```bash
git add src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
git commit -m "$(cat <<'EOF'
refactor(plugins): scanner persists record_counts breakdown

Replace _sum_scope_records / _ScopeRecordCountError shim with direct
calls to fetch_scope_counts_with_client. _fetch_counts now returns the
per-table breakdown; scan() dual-writes both record_count (sum) and
record_counts (tuple) so existing consumers stay green while consumers
migrate.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Orphans uses `total_records` helper

**Files:**
- Modify: `src/nexus/plugins/orphans.py`
- Modify: `tests/test_plugins_orphans.py`

Switch the filter predicate to `total_records(p) == 0`. Update test fixtures to pass `record_counts` instead of `record_count`. After this task, `orphans.py` no longer reads `record_count`.

- [ ] **Step 1: Update test fixture to use record_counts**

In `tests/test_plugins_orphans.py`, replace the `_plugin` helper (lines 16-36):

```python
def _plugin(
    plugin_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    state: str = "active",
    record_count: int | None = None,
) -> PluginInfo:
    """Build a PluginInfo with optional record_count translated to record_counts.

    ``record_count=0`` -> ``record_counts=()`` (empty -> sum 0).
    ``record_count=N>0`` -> single-bucket tuple summing to N.
    ``record_count=None`` -> ``record_counts=None`` (uncaptured).
    """
    if record_count is None:
        counts: tuple[ScopeRecordCount, ...] | None = None
    elif record_count == 0:
        counts = ()
    else:
        counts = (ScopeRecordCount(table="sys_script", count=record_count),)
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
            "record_counts": counts,
        }
    )
```

Add the `ScopeRecordCount` import at the top of the test file (insert in the existing import block):

```python
from nexus.plugins.models import PluginInfo, PluginInventory, ScopeRecordCount
```

The test bodies (lines 47-101) keep their `record_count=X` arguments; the helper now translates them. No test renaming required.

- [ ] **Step 2: Run orphan tests to verify they still pass (helper translates)**

Run: `pytest tests/test_plugins_orphans.py -v`

Expected: all tests PASS. `orphans.py` still reads `record_count`, scanner still dual-writes it, so behavior is unchanged. The helper just translates the test argument.

- [ ] **Step 3: Update `orphans.py` to use `total_records`**

In `src/nexus/plugins/orphans.py`, replace the file body:

```python
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
        p
        for p in inventory.plugins
        if p.plugin_id not in has_dependents and total_records(p) == 0
    ]
    orphans.sort(key=lambda p: (p.state, p.plugin_id))
    return tuple(orphans)
```

- [ ] **Step 4: Run orphan tests to verify they still pass with new predicate**

Run: `pytest tests/test_plugins_orphans.py -v`

Expected: all tests PASS. The filter is now `total_records(p) == 0`; the helper test fixture builds `record_counts=()` for `record_count=0`, which `total_records` returns 0 for.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/orphans.py tests/test_plugins_orphans.py
git commit -m "$(cat <<'EOF'
refactor(plugins): orphan detection uses total_records helper

orphan_candidates now filters via total_records(p) == 0 against the new
record_counts tuple field. Test fixture _plugin translates the legacy
record_count argument to record_counts for compatibility.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Impact cache-first fast-path + `live` param

**Files:**
- Modify: `src/nexus/plugins/impact.py`
- Modify: `tests/test_plugins_impact.py`

Replace the `record_count == 0` fast-path with a cache-first read of `record_counts`. Add `live: bool = False` parameter; when `True`, ignore the cache and always re-query SN.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_plugins_impact.py` (append at the end):

```python
def test_compute_impact_serves_from_cache_when_record_counts_populated() -> None:
    """Cached record_counts -> no live call, returned directly with counts_available=True."""
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)

    cached = (
        ScopeRecordCount(table="sys_script", count=100),
        ScopeRecordCount(table="sys_business_rule", count=25),
    )
    target = _plugin("com.target").model_copy(update={"record_counts": cached})
    inv = _inventory(target)

    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )

    assert call_count["n"] == 0
    assert result.counts_available is True
    assert result.record_counts == cached


def test_compute_impact_live_flag_forces_refetch_despite_cache() -> None:
    """live=True ignores cached record_counts and hits the live aggregate API."""
    live_payload = {
        "result": [
            {
                "stats": {"count": "999"},
                "groupby_fields": [{"field": "sys_class_name", "value": "sys_script"}],
            }
        ]
    }
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json=live_payload)

    transport = httpx.MockTransport(handler)

    cached = (ScopeRecordCount(table="sys_script", count=1),)
    target = _plugin("com.target").model_copy(update={"record_counts": cached})
    inv = _inventory(target)

    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
            live=True,
        )
    )

    assert call_count["n"] == 1
    assert result.counts_available is True
    assert result.record_counts == (ScopeRecordCount(table="sys_script", count=999),)


def test_compute_impact_falls_back_to_live_when_record_counts_none() -> None:
    """record_counts=None (uncaptured) triggers a live call, like today."""
    live_payload = {
        "result": [
            {
                "stats": {"count": "7"},
                "groupby_fields": [{"field": "sys_class_name", "value": "sys_script"}],
            }
        ]
    }
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json=live_payload)

    transport = httpx.MockTransport(handler)

    inv = _inventory(_plugin("com.target"))

    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )

    assert call_count["n"] == 1
    assert result.counts_available is True
    assert result.record_counts[0].count == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_impact.py::test_compute_impact_serves_from_cache_when_record_counts_populated tests/test_plugins_impact.py::test_compute_impact_live_flag_forces_refetch_despite_cache tests/test_plugins_impact.py::test_compute_impact_falls_back_to_live_when_record_counts_none -v`

Expected: 3 FAILs.
- The cache-serve test fails because `compute_impact` does not check `record_counts`; it always calls live.
- The `--live` flag test fails because `compute_impact` does not accept a `live` kwarg (`TypeError`).
- The fallback test currently passes by coincidence but the assertion shape differs; mark it red if not yet passing.

- [ ] **Step 3: Rewrite `compute_impact` in `src/nexus/plugins/impact.py`**

Replace `compute_impact` (lines 192-248) with:

```python
async def compute_impact(
    inventory: PluginInventory,
    target: str,
    *,
    url: str,
    token: str,
    transport: httpx.AsyncBaseTransport | None = None,
    live: bool = False,
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

    Returns:
        PluginImpact with reverse-deps and record counts.

        When ``live=False`` (default) and ``target.record_counts is not
        None``: serves cached breakdown directly, no live call.

        Otherwise: performs the live aggregate call. On failure,
        ``counts_available=False`` and ``record_counts=()``.

    Raises:
        PluginImpactError: If ``target`` is not present in the inventory.
    """
    deps = reverse_dependencies(inventory, target)
    target_info = next(p for p in inventory.plugins if p.plugin_id == target)

    if not live and target_info.record_counts is not None:
        return PluginImpact(
            target_plugin_id=target,
            target_name=target_info.name,
            reverse_deps=deps,
            record_counts=target_info.record_counts,
            counts_available=True,
        )

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

Update the module docstring (lines 5-11) to reflect the cache-first semantics:

```python
"""Plugin impact analysis layer.

Three-phase design:
    - ``reverse_dependencies`` -- pure BFS over the inventory.
    - ``fetch_scope_record_counts`` -- async aggregate API call.
    - ``compute_impact`` -- async orchestrator joining the two,
      cache-first against ``PluginInfo.record_counts`` with a
      ``live=True`` opt-in for forced refresh.
"""
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `pytest tests/test_plugins_impact.py::test_compute_impact_serves_from_cache_when_record_counts_populated tests/test_plugins_impact.py::test_compute_impact_live_flag_forces_refetch_despite_cache tests/test_plugins_impact.py::test_compute_impact_falls_back_to_live_when_record_counts_none -v`

Expected: 3 PASS.

- [ ] **Step 5: Run all impact tests**

Run: `pytest tests/test_plugins_impact.py -v`

Expected: all tests PASS. Existing fast-path test (the `record_count == 0` one) needs updating — see step 6.

- [ ] **Step 6: Update the legacy fast-path test if present**

Search `tests/test_plugins_impact.py` for any test that exercises the old `record_count == 0` fast-path. If a test exists with that name pattern (e.g., `test_compute_impact_skips_live_call_when_record_count_zero`), replace it with:

```python
def test_compute_impact_serves_empty_tuple_when_record_counts_is_empty() -> None:
    """record_counts=() means scope owns zero records -- serve cache, no live call."""
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)

    target = _plugin("com.target").model_copy(update={"record_counts": ()})
    inv = _inventory(target)

    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )

    assert call_count["n"] == 0
    assert result.record_counts == ()
    assert result.counts_available is True
```

If no such test exists, add this one — it covers the zero-records-cached path which used to be the only fast-path.

- [ ] **Step 7: Run the full suite**

Run: `pytest -q`

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/nexus/plugins/impact.py tests/test_plugins_impact.py
git commit -m "$(cat <<'EOF'
feat(plugins): impact serves cached record_counts; add live opt-in

compute_impact() reads PluginInfo.record_counts directly when populated,
skipping the live aggregate REST call entirely. New live=False parameter;
callers pass live=True to force a fresh query against the instance.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: CLI `--live` flag + orphans precheck swap

**Files:**
- Modify: `src/nexus/cli.py`
- Modify: `tests/test_cli_plugins_impact.py`
- Modify: `tests/test_cli_plugins_orphans.py`

Wire the `--live` flag through to `compute_impact`. Swap the orphans precheck (`cli.py:1930`) from `record_count` to `record_counts` -- this is what completes the `record_count` migration in production code.

- [ ] **Step 1: Write the failing CLI tests**

First, add `ScopeRecordCount` to the existing import in `tests/test_cli_plugins_impact.py`:

```python
from nexus.plugins.models import PluginInfo, PluginInventory, ScopeRecordCount
```

Then append at the end of the file:

```python
def test_plugins_impact_default_uses_cache(
    tmp_path: Path,
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default invocation serves from cached record_counts without hitting the network."""
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"result": []})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("nexus.cli._impact_transport", lambda: transport)

    cached_info = _info("com.target").model_copy(
        update={"record_counts": (ScopeRecordCount(table="sys_script", count=42),)}
    )
    _seed(tmp_path, "dev", (cached_info,))
    monkeypatch.setattr(
        "nexus.cli._acquire_token",
        lambda instance: (None, _meta("dev"), "t", datetime.now(UTC)),
    )

    result = runner.invoke(app, ["plugins", "impact", "com.target", "--instance", "dev"])
    assert result.exit_code == 0
    assert call_count["n"] == 0


def test_plugins_impact_live_flag_passes_through(
    tmp_path: Path,
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--live forces a fresh aggregate API call even when cache is populated."""
    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(
            200,
            json={
                "result": [
                    {
                        "stats": {"count": "99"},
                        "groupby_fields": [
                            {"field": "sys_class_name", "value": "sys_script"}
                        ],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr("nexus.cli._impact_transport", lambda: transport)

    cached_info = _info("com.target").model_copy(
        update={"record_counts": (ScopeRecordCount(table="sys_script", count=1),)}
    )
    _seed(tmp_path, "dev", (cached_info,))
    monkeypatch.setattr(
        "nexus.cli._acquire_token",
        lambda instance: (None, _meta("dev"), "t", datetime.now(UTC)),
    )

    result = runner.invoke(
        app, ["plugins", "impact", "com.target", "--instance", "dev", "--live"]
    )
    assert result.exit_code == 0
    assert call_count["n"] == 1
```

Update `tests/test_cli_plugins_orphans.py` precheck-warning test. Locate the test that asserts the warning fires when all plugins have no captured counts. Update its fixture to set `record_counts=None` instead of `record_count=None`. If the helper already centralizes the translation (it should after Task 3 if the file shares the pattern), grep for `record_count=` references and convert.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cli_plugins_impact.py::test_plugins_impact_default_uses_cache tests/test_cli_plugins_impact.py::test_plugins_impact_live_flag_passes_through -v`

Expected: 2 FAILs. The default-uses-cache test fails because the CLI does not check the cache before invoking compute_impact (compute_impact does, but the default test should make sure the wiring is correct). The `--live` test fails because the `--live` flag is not declared on the typer command.

- [ ] **Step 3: Update `plugins_impact` in `src/nexus/cli.py`**

Replace the `plugins_impact` function signature and body (lines 1795-1835):

```python
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
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
    live: Annotated[
        bool,
        typer.Option(
            "--live",
            help="Force re-query of SN record counts; ignore the cached breakdown.",
        ),
    ] = False,
) -> None:
    """Show reverse dependencies + scope-owned record counts for a plugin."""
    _validate_format(output_format)
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
                live=live,
            )
        )
    except PluginImpactError as exc:
        console.print(Notice.error(f"Plugin not found: {plugin_id}"))
        raise typer.Exit(1) from exc

    if output_format == "json":
        _emit_json(impact)
        return
    _render_impact(impact)
```

- [ ] **Step 4: Update the orphans precheck (line 1930)**

In `src/nexus/cli.py`, find the `plugins_orphans` function and locate the precheck:

```python
    if all(p.record_count is None for p in inventory.plugins):
```

Replace with:

```python
    if all(p.record_counts is None for p in inventory.plugins):
```

- [ ] **Step 5: Run new and updated CLI tests**

Run: `pytest tests/test_cli_plugins_impact.py tests/test_cli_plugins_orphans.py -v`

Expected: all tests PASS.

- [ ] **Step 6: Run the full suite**

Run: `pytest -q`

Expected: all tests PASS. The orphans precheck now reads `record_counts`; scanner still dual-writes both fields so behavior is preserved for any other read path.

- [ ] **Step 7: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_impact.py tests/test_cli_plugins_orphans.py
git commit -m "$(cat <<'EOF'
feat(plugins): --live flag on plugins impact; orphans precheck swap

plugins impact gains --live to bypass the cached record_counts breakdown
and force a fresh SN aggregate query. plugins orphans precheck now reads
record_counts instead of the soon-to-be-removed record_count field.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Drop `record_count` from model and scanner

**Files:**
- Modify: `src/nexus/plugins/models.py`
- Modify: `src/nexus/plugins/scanner.py`
- Modify: `tests/test_plugins_models.py`
- Modify: `tests/test_plugins_scanner.py`
- Modify: `tests/test_plugins_orphans.py`

At this point no production code reads `record_count`. Remove the field and the dual-write.

- [ ] **Step 1: Remove the field from `PluginInfo`**

In `src/nexus/plugins/models.py`, delete the `record_count: int | None = None` line and remove the `record_count:` entry from the class docstring. The remaining field set:

```python
    latest_version: str | None = None
    vendor: str = ""
    record_counts: tuple[ScopeRecordCount, ...] | None = None
```

The class docstring keeps only the `record_counts:` entry.

- [ ] **Step 2: Remove dual-write from `scanner.py`**

In `src/nexus/plugins/scanner.py`, the `scan()` block becomes:

```python
            if capture_counts:
                breakdown = await _fetch_counts(client, tuple(by_id.keys()))
                by_id = {
                    pid: info.model_copy(update={"record_counts": breakdown.get(pid)})
                    for pid, info in by_id.items()
                }
```

Delete the `_total_or_none` helper function. It is no longer needed.

- [ ] **Step 3: Update `tests/test_plugins_models.py` — drop record_count tests**

Delete the three `record_count`-focused tests (the helper `_info` does not pass it, so this is just removing the explicit-construction tests):

- `test_plugin_info_accepts_record_count_field`
- `test_plugin_info_defaults_record_count_to_none`
- `test_plugin_info_accepts_record_count_zero`

- [ ] **Step 4: Update `tests/test_plugins_scanner.py` — drop record_count tests**

Delete:

- `test_scan_populates_record_count_from_aggregate_api`
- `test_scan_sets_record_count_none_when_aggregate_call_fails`

(These were superseded by `test_scan_populates_record_counts_breakdown` and `test_scan_sets_record_counts_none_when_aggregate_call_fails` added in Task 2.)

Update `test_scan_keeps_other_fields_intact_after_count_capture` to assert against `record_counts` if it currently asserts `record_count`. The assertion lines should be `incident.record_counts == (ScopeRecordCount(table="sys_script", count=5),)`.

Update `test_scan_skips_count_fan_out_when_capture_counts_false` -- replace the assertion `assert all(p.record_count is None for p in inv.plugins)` with `assert all(p.record_counts is None for p in inv.plugins)`.

Add the `ScopeRecordCount` import to the file:

```python
from nexus.plugins.models import PluginInventory, ScopeRecordCount
```

- [ ] **Step 5: Update `tests/test_plugins_orphans.py` — drop translation helper**

Replace the `_plugin` helper (from Task 3) with a cleaner version that takes `record_counts` directly. Bulk-update all call sites:

```python
def _plugin(
    plugin_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    state: str = "active",
    record_counts: tuple[ScopeRecordCount, ...] | None = None,
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
            "record_counts": record_counts,
        }
    )
```

Update each test that called `_plugin(..., record_count=N)`:

- `record_count=0` -> `record_counts=()`
- `record_count=42` -> `record_counts=(ScopeRecordCount(table="sys_script", count=42),)`
- `record_count=100` -> `record_counts=(ScopeRecordCount(table="sys_script", count=100),)`
- `record_count=None` -> `record_counts=None` (or omit, since it is the default)

Affected tests (each test body's call sites need updating):

- `test_orphan_candidates_returns_plugin_with_zero_deps_and_zero_records`
- `test_orphan_candidates_excludes_plugin_with_dependents`
- `test_orphan_candidates_excludes_plugin_with_records`
- `test_orphan_candidates_excludes_plugin_with_record_count_none`
- `test_orphan_candidates_includes_inactive_plugins`
- `test_orphan_candidates_excludes_plugin_in_its_own_depends_on`
- `test_orphan_candidates_sorts_by_state_then_plugin_id`
- `test_orphan_candidates_returns_empty_tuple_when_no_candidates`

- [ ] **Step 6: Run the full suite to verify the field is fully removed**

Run: `pytest -q`

Expected: all tests PASS.

- [ ] **Step 7: Verify no stale references remain**

Run: `grep -rn "record_count[^s]" src/nexus tests`

Expected: no hits matching `record_count` (without trailing `s`) inside `src/nexus/plugins/` or any plugin-related test file. The only acceptable hits are in `src/nexus/capture/*` and `tests/capture/*` (unrelated `manifest.record_count` concept).

- [ ] **Step 8: Commit**

```bash
git add src/nexus/plugins/models.py src/nexus/plugins/scanner.py tests/test_plugins_models.py tests/test_plugins_scanner.py tests/test_plugins_orphans.py
git commit -m "$(cat <<'EOF'
refactor(plugins): drop record_count scalar; record_counts is canonical

PluginInfo.record_count removed. Scanner writes only record_counts.
Tests updated to construct fixtures with the tuple shape directly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Registry invalidates legacy-shape files

**Files:**
- Modify: `src/nexus/instances/registry.py`
- Modify: `tests/test_instances_registry.py`

After Task 6, any on-disk `plugins.json` or `plugins.baseline.json` written by a previous NEXUS version (which had `record_count`) fails Pydantic validation because of `extra="forbid"`. Catch `ValidationError`, log a refresh hint, return None.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_instances_registry.py`:

```python
def test_load_plugin_inventory_with_legacy_shape_returns_none_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A plugins.json file with the old record_count field is treated as absent."""
    import logging

    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev"))

    legacy_inventory = {
        "captured_at": "2026-05-01T12:00:00+00:00",
        "sn_version": "Xanadu",
        "plugins": [
            {
                "plugin_id": "com.snc.incident",
                "name": "Incident",
                "version": "1.0",
                "state": "active",
                "source": "servicenow",
                "product_family": "ITSM",
                "depends_on": [],
                "sys_id": "sys-1",
                "installed_at": None,
                "record_count": 42,
            }
        ],
    }
    import json

    (tmp_path / "dev" / "plugins.json").write_text(
        json.dumps(legacy_inventory), encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING, logger="nexus.instances.registry"):
        result = registry.load_plugin_inventory("dev")

    assert result is None
    assert any("schema outdated" in rec.message for rec in caplog.records)


def test_load_plugin_baseline_with_legacy_shape_returns_none_and_warns(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A plugins.baseline.json file with the old record_count field is treated as absent."""
    import logging

    registry = InstanceRegistry(tmp_path)
    registry.register(_meta("dev"))

    legacy_baseline = {
        "captured_at": "2026-05-01T12:00:00+00:00",
        "sn_version": "Xanadu",
        "plugins": [
            {
                "plugin_id": "com.snc.incident",
                "name": "Incident",
                "version": "1.0",
                "state": "active",
                "source": "servicenow",
                "product_family": "ITSM",
                "depends_on": [],
                "sys_id": "sys-1",
                "installed_at": None,
                "record_count": 0,
            }
        ],
    }
    import json

    (tmp_path / "dev" / "plugins.baseline.json").write_text(
        json.dumps(legacy_baseline), encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING, logger="nexus.instances.registry"):
        result = registry.load_plugin_baseline("dev")

    assert result is None
    assert any("baseline" in rec.message.lower() for rec in caplog.records)
```

If `_meta` is not already defined in the test file at top level, reuse the existing `_meta` helper at the top of `test_instances_registry.py` (line 18 in the snapshot read above).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_instances_registry.py::test_load_plugin_inventory_with_legacy_shape_returns_none_and_warns tests/test_instances_registry.py::test_load_plugin_baseline_with_legacy_shape_returns_none_and_warns -v`

Expected: 2 FAILs. Both raise `ValidationError` because the legacy file has the now-forbidden `record_count` field and the load methods do not catch the error.

- [ ] **Step 3: Update `load_plugin_inventory` and `load_plugin_baseline` in `src/nexus/instances/registry.py`**

Replace `load_plugin_inventory` (lines 146-164):

```python
    def load_plugin_inventory(self, profile: str) -> PluginInventory | None:
        """Read plugins.json for a profile if it exists.

        Args:
            profile: Profile name.

        Returns:
            PluginInventory or None if the profile exists but no inventory
            captured yet -- or if the on-disk file is unreadable / has a
            stale schema (caller is told via WARNING log to refresh).

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        inv_file = profile_dir / _PLUGIN_INVENTORY
        if not inv_file.exists():
            return None
        try:
            return PluginInventory.model_validate_json(inv_file.read_text(encoding="utf-8"))
        except ValidationError:
            log.warning(
                "plugins.json schema outdated for profile=%s -- "
                "run 'nexus instance refresh' to rebuild",
                profile,
            )
            return None
```

Replace `load_plugin_baseline` (lines 178-196):

```python
    def load_plugin_baseline(self, profile: str) -> PluginInventory | None:
        """Read plugins.baseline.json for a profile if it exists.

        Args:
            profile: Profile name.

        Returns:
            PluginInventory or None if no baseline has been ack'd yet --
            or if the on-disk file is unreadable / has a stale schema
            (caller is told via WARNING log to re-ack the baseline).

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        baseline_file = profile_dir / _PLUGIN_BASELINE
        if not baseline_file.exists():
            return None
        try:
            return PluginInventory.model_validate_json(
                baseline_file.read_text(encoding="utf-8")
            )
        except ValidationError:
            log.warning(
                "plugins.baseline.json schema outdated for profile=%s -- "
                "run 'nexus plugins drift --ack' to re-ack the baseline",
                profile,
            )
            return None
```

- [ ] **Step 4: Run new tests to verify they pass**

Run: `pytest tests/test_instances_registry.py::test_load_plugin_inventory_with_legacy_shape_returns_none_and_warns tests/test_instances_registry.py::test_load_plugin_baseline_with_legacy_shape_returns_none_and_warns -v`

Expected: 2 PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/instances/registry.py tests/test_instances_registry.py
git commit -m "$(cat <<'EOF'
feat(instances): invalidate legacy-shape plugins.json on load

load_plugin_inventory and load_plugin_baseline now catch ValidationError
(triggered by the dropped record_count field on pre-I inventories) and
return None with a refresh-hint WARNING. Pre-release tool; no in-place
migrator.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Scanner switches to Link-header pagination

**Files:**
- Modify: `src/nexus/plugins/scanner.py`
- Modify: `tests/test_plugins_scanner.py`

Replace `sysparm_offset` arithmetic and the partial-page-break heuristic with RFC 5988 Link header walking. Independent of the record-counts change; could ship separately, but stays in this sub-project.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_plugins_scanner.py` (append at end):

```python
def test_parse_next_link_returns_url_for_rel_next() -> None:
    from nexus.plugins.scanner import _parse_next_link

    header = '<https://x.example/api?offset=200>;rel="next",<https://x.example/api?offset=0>;rel="first"'
    assert _parse_next_link(header) == "https://x.example/api?offset=200"


def test_parse_next_link_returns_none_when_no_next_rel() -> None:
    from nexus.plugins.scanner import _parse_next_link

    header = '<https://x.example/api?offset=0>;rel="first",<https://x.example/api?offset=400>;rel="last"'
    assert _parse_next_link(header) is None


def test_parse_next_link_returns_none_for_empty_header() -> None:
    from nexus.plugins.scanner import _parse_next_link

    assert _parse_next_link("") is None


def test_parse_next_link_returns_none_for_malformed_header() -> None:
    from nexus.plugins.scanner import _parse_next_link

    assert _parse_next_link("not a link header") is None


def test_parse_next_link_tolerates_whitespace_and_unquoted_rel() -> None:
    from nexus.plugins.scanner import _parse_next_link

    header = "<https://x.example/api?offset=200> ; rel=next"
    assert _parse_next_link(header) == "https://x.example/api?offset=200"


def test_fetch_follows_link_header_next() -> None:
    """Two pages stitched via Link rel='next'."""
    pages = [
        (
            [
                {
                    "sys_id": f"a{i}",
                    "id": f"com.p{i}",
                    "name": f"P{i}",
                    "version": "1.0",
                    "active": "true",
                    "dependencies": "",
                    "installed_on": "",
                }
                for i in range(200)
            ],
            "https://x.example/api/now/table/v_plugin?sysparm_offset=200",
        ),
        (
            [
                {
                    "sys_id": f"b{i}",
                    "id": f"com.q{i}",
                    "name": f"Q{i}",
                    "version": "1.0",
                    "active": "true",
                    "dependencies": "",
                    "installed_on": "",
                }
                for i in range(50)
            ],
            None,
        ),
    ]
    call_idx = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        if "v_plugin" in req.url.path:
            page, next_url = pages[call_idx["i"]]
            call_idx["i"] += 1
            headers = {"Link": f'<{next_url}>;rel="next"'} if next_url else {}
            return httpx.Response(200, json={"result": page}, headers=headers)
        if "sys_store_app" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = asyncio.run(_scan(transport))
    v_plugin_count = sum(1 for p in inv.plugins if p.plugin_id.startswith("com."))
    assert v_plugin_count == 250


def test_fetch_stops_when_no_next_link_on_full_page() -> None:
    """A full 200-row page WITHOUT Link rel='next' must terminate (the bug the old heuristic missed)."""

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        if "v_plugin" in req.url.path:
            page = [
                {
                    "sys_id": f"s{i}",
                    "id": f"com.p{i}",
                    "name": f"P{i}",
                    "version": "1.0",
                    "active": "true",
                    "dependencies": "",
                    "installed_on": "",
                }
                for i in range(200)
            ]
            return httpx.Response(200, json={"result": page})
        if "sys_store_app" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = asyncio.run(_scan(transport))
    v_plugin_count = sum(1 for p in inv.plugins if p.plugin_id.startswith("com."))
    assert v_plugin_count == 200
```

Delete the existing test `test_fetch_paginates_through_multiple_pages` (it uses `sysparm_offset`-based pagination logic, which is being replaced). Delete the existing test `test_fetch_stops_at_max_pages_with_warning` and replace with the Link-header-driven version:

```python
def test_fetch_stops_at_max_pages_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Handler always returns a Link rel='next' so the loop must bail at _MAX_PAGES."""

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        if "v_plugin" in req.url.path:
            offset = int(req.url.params.get("sysparm_offset", "0"))
            page = [
                {
                    "sys_id": f"s{offset + i}",
                    "id": f"com.p{offset + i}",
                    "name": f"P{offset + i}",
                    "version": "1.0",
                    "active": "true",
                    "dependencies": "",
                    "installed_on": "",
                }
                for i in range(200)
            ]
            next_url = f"https://x.example/api/now/table/v_plugin?sysparm_offset={offset + 200}"
            return httpx.Response(
                200,
                json={"result": page},
                headers={"Link": f'<{next_url}>;rel="next"'},
            )
        if "sys_store_app" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    with caplog.at_level(logging.WARNING, logger="nexus.plugins.scanner"):
        inv = asyncio.run(_scan(transport))
    assert any("exceeded" in rec.message for rec in caplog.records)
    # Total rows = _MAX_PAGES (50) * _PAGE_LIMIT (200) = 10000 dedup'd
    assert len(inv.plugins) == 10000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_plugins_scanner.py -v -k "parse_next_link or follows_link_header or stops_when_no_next_link or stops_at_max_pages"`

Expected: all FAILs. `_parse_next_link` does not exist; `_fetch` does not consult the Link header.

- [ ] **Step 3: Add `_parse_next_link` and rewrite `_fetch`**

In `src/nexus/plugins/scanner.py`:

1. Add `import re` to the top imports.

2. Below the module-level constants (after `_CUSTOM_SCOPE_PREFIXES`), add:

```python
_NEXT_LINK_RE = re.compile(r'<([^>]+)>\s*;\s*rel\s*=\s*"?next"?', re.IGNORECASE)


def _parse_next_link(header: str) -> str | None:
    """Return the URL marked rel="next" in an RFC 5988 Link header, or None.

    Tolerant of whitespace and unquoted rel values. Returns the first match;
    SN responses contain at most one rel="next" entry.

    Args:
        header: Raw value of the ``Link`` response header, or ``""``.

    Returns:
        The URL inside angle brackets paired with ``rel="next"``, else None.
    """
    if not header:
        return None
    match = _NEXT_LINK_RE.search(header)
    return match.group(1) if match else None
```

3. Replace `_fetch` (lines 118-162) entirely:

```python
    async def _fetch(
        self, client: httpx.AsyncClient, table: str, fields: str
    ) -> tuple[list[dict[str, object]], tuple[str, int] | None]:
        """Fetch a Table API endpoint, walking RFC 5988 Link rel="next" headers.

        Args:
            client: Open httpx.AsyncClient bound to the instance URL.
            table: Table name (e.g. ``v_plugin``).
            fields: Comma-separated field list for ``sysparm_fields``.

        Returns:
            ``(rows, None)`` on success; ``([], (table, status))`` on the
            first non-200 response. Pagination follows the ``Link`` header
            with ``rel="next"`` until absent. A safety cap of
            ``_MAX_PAGES`` aborts runaway loops with a WARNING.
        """
        rows: list[dict[str, object]] = []
        resp = await client.get(
            f"/api/now/table/{table}",
            params={"sysparm_fields": fields, "sysparm_limit": _PAGE_LIMIT},
        )
        for _ in range(_MAX_PAGES):
            if resp.status_code != 200:
                log.warning("plugin scan: %s returned HTTP %d", table, resp.status_code)
                return [], (table, resp.status_code)
            rows.extend(resp.json().get("result", []))
            next_url = _parse_next_link(resp.headers.get("Link", ""))
            if next_url is None:
                return rows, None
            resp = await client.get(next_url)
        else:
            log.warning(
                "plugin scan: %s exceeded %d pages (%d rows); truncating",
                table,
                _MAX_PAGES,
                len(rows),
            )
        return rows, None
```

- [ ] **Step 4: Run scanner tests**

Run: `pytest tests/test_plugins_scanner.py -v`

Expected: all tests PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest -q`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
git commit -m "$(cat <<'EOF'
feat(plugins): scanner pagination via RFC 5988 Link header

_fetch now follows resp.headers['Link'] rel="next" instead of breaking
on the partial-page heuristic, which silently truncated when SN returned
a full-but-last page. New _parse_next_link helper + _NEXT_LINK_RE regex
covers quoted/unquoted rel values with tolerant whitespace.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Coverage ratchet bump + final green run

**Files:**
- Modify: `.ratchet.json`

After all per-task green runs, the per-module covered_lines for modules touched in this sub-project will have changed (some up, some neutral). The ratchet must be updated so the post-edit hook does not block subsequent edits.

- [ ] **Step 1: Run the full coverage report**

Run:

```bash
pytest -q --cov=nexus.plugins.models --cov=nexus.plugins.scanner --cov=nexus.plugins.orphans --cov=nexus.plugins.impact --cov=nexus.instances.registry --cov-report=json --cov-fail-under=0
```

Expected: all tests pass; `coverage.json` written to repo root.

- [ ] **Step 2: Read the new per-module covered_lines**

Open `coverage.json`, find the `files` section, and extract the `summary.covered_lines` for each of:

- `src/nexus/plugins/models.py`
- `src/nexus/plugins/scanner.py`
- `src/nexus/plugins/orphans.py`
- `src/nexus/plugins/impact.py`
- `src/nexus/instances/registry.py`

Note Windows uses backslashes in the file_key (`src\\nexus\\plugins\\models.py`). Normalize to forward slashes for the module-name lookup.

- [ ] **Step 3: Update `.ratchet.json`**

Edit `.ratchet.json` and update the `modules.<dotted_module>.covered_lines` value for each module listed above to the new value from the coverage report. Do not touch other fields.

Example shape (use real numbers from the coverage report):

```json
{
  "modules": {
    "nexus.plugins.models": {"covered_lines": 95},
    "nexus.plugins.scanner": {"covered_lines": 138},
    "nexus.plugins.orphans": {"covered_lines": 16},
    "nexus.plugins.impact": {"covered_lines": 78},
    "nexus.instances.registry": {"covered_lines": 92}
  }
}
```

- [ ] **Step 4: Run the full suite one more time**

Run: `pytest -q`

Expected: all tests PASS.

- [ ] **Step 5: Run all linters + type checkers**

Run: `pre-commit run --all-files`

Expected: all hooks PASS (black, ruff, mypy, pyright, semgrep, pytest).

- [ ] **Step 6: Commit**

```bash
git add .ratchet.json
git commit -m "$(cat <<'EOF'
chore(ratchet): bump coverage baselines after sub-project I

Per-module covered_lines updated for plugins/{models,scanner,orphans,impact}
and instances/registry after the record_counts migration and Link-header
pagination changes landed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes

**Spec coverage (every requirement -> task):**

- Model field shift to `record_counts: tuple[ScopeRecordCount, ...] | None` -> Task 1 (add), Task 6 (drop old)
- `total_records` helper -> Task 1
- Scanner preserves breakdown (no sum/discard) -> Task 2, Task 6 (cleanup)
- Orphan detection uses helper -> Task 3
- Impact cache-first fast-path -> Task 4
- `--live` flag at module level -> Task 4
- `--live` flag on CLI -> Task 5
- CLI precheck swap -> Task 5
- Registry invalidates legacy-shape files -> Task 7
- Scanner Link-header pagination + `_parse_next_link` -> Task 8
- Ratchet bump -> Task 9

**Type consistency:** `record_counts: tuple[ScopeRecordCount, ...] | None` is the single field shape used throughout. `total_records(info) -> int | None`. `compute_impact(..., live: bool = False)`. `_parse_next_link(header: str) -> str | None`. `_fetch_counts -> dict[str, tuple[ScopeRecordCount, ...] | None]`.

**Atomicity:** Each task's commit produces a green full suite (verified via `pytest -q` step at the end of each task). The transient dual-write in Task 2 is removed in Task 6 -- no shim survives the sub-project.

**Out-of-scope confirmations:** No diff/drift modification; no capture-layer touch; no schema versioning; no public re-export of `total_records`. All matches the spec.
