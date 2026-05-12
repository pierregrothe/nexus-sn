# Plugin Cleanups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship six surgical cleanups noted while building sub-projects A-D3: scanner pagination fix, DRY consolidation of the Aggregate-API call, cached-count fast-path in impact, `--no-counts` flag on refresh, `--format json` across seven plugin commands, and `--strict` CI-gating flag on advisories.

**Architecture:** Local edits to three existing files (`scanner.py`, `impact.py`, `cli.py`). No new modules, no new Pydantic data models in `nexus.plugins.models` (two inline wrapper models live in `cli.py` for JSON output only). Each of the six items is independent and lands as its own commit.

**Tech Stack:** Python 3.14, Pydantic v2 (frozen+strict+extra=forbid), httpx, asyncio.Semaphore, Typer.

**Branch:** `feat/plugins-cleanups` (already created, spec committed at `e6e6f3f`, validation update at `65e0bf9`).

**Spec:** `docs/superpowers/specs/2026-05-12-plugin-cleanups-design.md`

---

## File Map

**Modified:**
- `src/nexus/plugins/scanner.py` -- items 1, 2, 4
- `src/nexus/plugins/impact.py` -- items 2, 3
- `src/nexus/cli.py` -- items 3, 4, 6, 7
- `tests/test_plugins_scanner.py` -- 3 new tests
- `tests/test_plugins_impact.py` -- 4 new tests
- `tests/test_cli_instance.py` -- 1 new test (refresh `--no-counts`)
- `tests/test_cli_plugins.py` (list/info live here per existing convention) -- 4 new tests (2 each * 2 commands)
- `tests/test_cli_plugins_diff.py` -- 2 new tests
- `tests/test_cli_plugins_advisories.py` -- 5 new tests (2 for --format + 3 for --strict)
- `tests/test_cli_plugins_updates.py` -- 2 new tests
- `tests/test_cli_plugins_impact.py` -- 2 new tests
- `tests/test_cli_plugins_orphans.py` -- 2 new tests
- `.ratchet.json` -- baseline bumps for cli.py, scanner.py, impact.py

---

## Task 1: Scanner pagination loop

**Files:**
- Modify: `src/nexus/plugins/scanner.py` (`_fetch` method around lines 97-109; add `_MAX_PAGES` constant near line 28)
- Modify: `tests/test_plugins_scanner.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_scanner.py`:

```python
def test_fetch_paginates_through_multiple_pages() -> None:
    """Three pages: 200 + 200 + 50 = 450 rows total."""
    pages = [
        [{"sys_id": f"a{i}", "id": f"com.p{i}", "name": f"P{i}", "version": "1.0", "active": "true", "dependencies": "", "installed_on": ""} for i in range(200)],
        [{"sys_id": f"b{i}", "id": f"com.q{i}", "name": f"Q{i}", "version": "1.0", "active": "true", "dependencies": "", "installed_on": ""} for i in range(200)],
        [{"sys_id": f"c{i}", "id": f"com.r{i}", "name": f"R{i}", "version": "1.0", "active": "true", "dependencies": "", "installed_on": ""} for i in range(50)],
    ]

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        if "v_plugin" in req.url.path:
            offset = int(req.url.params.get("sysparm_offset", "0"))
            page_idx = offset // 200
            page = pages[page_idx] if page_idx < len(pages) else []
            return httpx.Response(200, json={"result": page})
        if "sys_store_app" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = asyncio.run(_scan(transport))
    v_plugin_count = sum(1 for p in inv.plugins if p.plugin_id.startswith("com."))
    assert v_plugin_count == 450


def test_fetch_stops_at_max_pages_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Handler always returns 200 rows -> loop should bail at _MAX_PAGES."""
    full_page = [
        {"sys_id": f"a{i}", "id": f"com.p{i}", "name": f"P{i}", "version": "1.0", "active": "true", "dependencies": "", "installed_on": ""}
        for i in range(200)
    ]

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(200, json={"result": []})
        if "v_plugin" in req.url.path:
            return httpx.Response(200, json={"result": full_page})
        if "sys_store_app" in req.url.path:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    import logging

    with caplog.at_level(logging.WARNING, logger="nexus.plugins.scanner"):
        inv = asyncio.run(_scan(transport))
    assert any("exceeded" in rec.message for rec in caplog.records)
    # Total rows = _MAX_PAGES (50) * _PAGE_LIMIT (200) = 10000 dedup'd
    assert len(inv.plugins) == 10000
```

The `import logging` at the top of the helper test is acceptable as a function-local import in the test fixture context. Hoist to module-top in step 4 if ruff PLC0415 fires.

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_scanner.py -v -k "paginates or stops_at_max_pages"`

Expected: `test_fetch_paginates_through_multiple_pages` returns 200 rows (current behavior), not 450. `test_fetch_stops_at_max_pages_with_warning` returns 200 rows and no warning.

- [ ] **Step 3: Modify `src/nexus/plugins/scanner.py`**

Add a new constant near line 28 (next to `_PAGE_LIMIT`):

```python
_MAX_PAGES = 50  # safety cap; 50 * 200 = 10,000 rows
```

Replace the `_fetch` method body:

```python
async def _fetch(
    self, client: httpx.AsyncClient, table: str, fields: str
) -> tuple[list[dict[str, object]], tuple[str, int] | None]:
    """Fetch a Table API endpoint, paginated until exhausted.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        table: Table name (e.g. ``v_plugin``).
        fields: Comma-separated field list for ``sysparm_fields``.

    Returns:
        ``(rows, None)`` on success; ``([], (table, status))`` on the
        first non-200 response. Pagination uses ``sysparm_offset``
        with a hard cap of ``_MAX_PAGES`` pages; if the cap is hit a
        WARNING is logged and partial data returned.
    """
    rows: list[dict[str, object]] = []
    offset = 0
    for _ in range(_MAX_PAGES):
        resp = await client.get(
            f"/api/now/table/{table}",
            params={
                "sysparm_fields": fields,
                "sysparm_limit": _PAGE_LIMIT,
                "sysparm_offset": offset,
            },
        )
        if resp.status_code != 200:
            log.warning("plugin scan: %s returned HTTP %d", table, resp.status_code)
            return [], (table, resp.status_code)
        page: list[dict[str, object]] = resp.json().get("result", [])
        if not page:
            break
        rows.extend(page)
        if len(page) < _PAGE_LIMIT:
            break
        offset += _PAGE_LIMIT
    else:
        log.warning(
            "plugin scan: %s exceeded %d pages (%d rows); truncating",
            table,
            _MAX_PAGES,
            len(rows),
        )
    return rows, None
```

The `for ... else` form: `else` runs when the loop completes without `break`, i.e. when the page cap is hit. Note the dedupe in `scan()` -- 10,000 distinct plugin_ids in the test means 10,000 plugins in the output (each row has a unique `id`).

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_scanner.py -v`

Expected: all scanner tests pass (existing + 2 new).

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
.venv/Scripts/pyright src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
```

```bash
git add src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
git commit -m "fix(plugins): paginate scanner _fetch (fix pre-existing 200-row truncation)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: DRY consolidation -- shared aggregate-API helper

**Files:**
- Modify: `src/nexus/plugins/impact.py` (extract helper, simplify wrapper)
- Modify: `src/nexus/plugins/scanner.py` (`_sum_scope_records` delegates)
- Modify: `tests/test_plugins_impact.py` (one new direct test)

- [ ] **Step 1: Write failing test**

Append to `tests/test_plugins_impact.py`:

```python
from nexus.plugins.impact import _fetch_scope_counts_with_client


async def _direct(transport: httpx.MockTransport) -> tuple:
    async with httpx.AsyncClient(
        base_url="https://x.example",
        headers={"Authorization": "Bearer t"},
        transport=transport,
    ) as client:
        return await _fetch_scope_counts_with_client(client, "com.x")


def test_fetch_scope_counts_with_client_returns_typed_buckets() -> None:
    transport = _stats_transport(
        payload=_stats_response([_row("sys_script", 7)]),
    )
    buckets = asyncio.run(_direct(transport))
    assert len(buckets) == 1
    assert buckets[0].table == "sys_script"
    assert buckets[0].count == 7
```

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py::test_fetch_scope_counts_with_client_returns_typed_buckets -v`

Expected: ImportError -- `_fetch_scope_counts_with_client` not defined yet.

- [ ] **Step 3: Refactor `src/nexus/plugins/impact.py`**

Extract a new private module-level helper. Replace the body of `fetch_scope_record_counts` to delegate. The current implementation (lines 105-167) becomes:

```python
async def _fetch_scope_counts_with_client(
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
            return await _fetch_scope_counts_with_client(client, plugin_id)
    except httpx.RequestError as exc:
        raise ScopeRecordCountError(f"network error: {exc}") from exc
```

`__all__` is unchanged -- `_fetch_scope_counts_with_client` stays private.

- [ ] **Step 4: Refactor `scanner._sum_scope_records`**

Replace the existing `_sum_scope_records` body (around scanner.py:187) with a delegation:

```python
async def _sum_scope_records(client: httpx.AsyncClient, plugin_id: str) -> int:
    """Return total records in ``plugin_id``'s scope (sum of per-table buckets).

    Delegates to ``nexus.plugins.impact._fetch_scope_counts_with_client``
    to avoid duplicating the aggregate-API request shape and response
    parsing. The import is function-local to avoid a top-level import
    cycle if impact.py ever grows scanner-side imports.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        plugin_id: Scope identifier.

    Returns:
        Sum of per-table record counts in the plugin's scope.

    Raises:
        _ScopeRecordCountError: On non-200 status or malformed response.
    """
    from nexus.plugins.impact import (
        ScopeRecordCountError,
        _fetch_scope_counts_with_client,
    )

    try:
        buckets = await _fetch_scope_counts_with_client(client, plugin_id)
    except ScopeRecordCountError as exc:
        raise _ScopeRecordCountError(str(exc)) from exc
    return sum(b.count for b in buckets)
```

Note: ruff PLC0415 flags function-local imports. The docstring above explains the cycle-avoidance reason; if PLC0415 blocks, add a per-line noqa is FORBIDDEN -- instead, hoist the import to module-top of scanner.py. The cycle risk is theoretical (impact.py doesn't import scanner.py today). Try the local import first; fall back to top-level if PLC0415 flags it.

Actually, just hoist it to module top -- pragmatic over theoretical:

Add to the top of scanner.py imports:

```python
from nexus.plugins.impact import (
    ScopeRecordCountError as _ImpactScopeRecordCountError,
    _fetch_scope_counts_with_client,
)
```

The alias `_ImpactScopeRecordCountError` avoids shadowing scanner's own `_ScopeRecordCountError`. Then `_sum_scope_records` becomes:

```python
async def _sum_scope_records(client: httpx.AsyncClient, plugin_id: str) -> int:
    """Return total records in ``plugin_id``'s scope (sum of per-table buckets).

    Delegates to ``nexus.plugins.impact._fetch_scope_counts_with_client``
    so the aggregate-API request shape lives in exactly one place.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        plugin_id: Scope identifier.

    Returns:
        Sum of per-table record counts in the plugin's scope.

    Raises:
        _ScopeRecordCountError: On non-200 status or malformed response.
    """
    try:
        buckets = await _fetch_scope_counts_with_client(client, plugin_id)
    except _ImpactScopeRecordCountError as exc:
        raise _ScopeRecordCountError(str(exc)) from exc
    return sum(b.count for b in buckets)
```

- [ ] **Step 5: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py tests/test_plugins_scanner.py -v`

Expected: all impact + scanner tests pass (existing + 1 new direct test).

- [ ] **Step 6: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/impact.py src/nexus/plugins/scanner.py tests/test_plugins_impact.py
.venv/Scripts/pyright src/nexus/plugins/impact.py src/nexus/plugins/scanner.py tests/test_plugins_impact.py
```

Both: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add src/nexus/plugins/impact.py src/nexus/plugins/scanner.py tests/test_plugins_impact.py
git commit -m "refactor(plugins): extract _fetch_scope_counts_with_client (DRY)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: compute_impact uses cached counts (zero case)

**Files:**
- Modify: `src/nexus/plugins/impact.py` (`compute_impact` body)
- Modify: `tests/test_plugins_impact.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_impact.py`:

```python
def _inventory_with_target(
    plugin_id: str,
    *,
    record_count: int | None,
) -> PluginInventory:
    return _inventory(_plugin(plugin_id).model_copy(update={"record_count": record_count}))


def test_compute_impact_skips_live_call_when_cached_record_count_is_zero() -> None:
    """Cached zero -> no stats request, counts_available True, record_counts empty."""
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
            return httpx.Response(200, json={"result": []})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = _inventory_with_target("com.target", record_count=0)
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )
    assert stats_calls == []
    assert result.counts_available is True
    assert result.record_counts == ()


def test_compute_impact_calls_live_when_cached_record_count_is_positive() -> None:
    """Cached > 0 -> live call still made to get per-table breakdown."""
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "stats": {"count": "5"},
                            "groupby_fields": [
                                {"field": "sys_class_name", "value": "sys_script"}
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = _inventory_with_target("com.target", record_count=42)
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )
    assert len(stats_calls) == 1
    assert result.counts_available is True
    assert len(result.record_counts) == 1


def test_compute_impact_calls_live_when_cached_record_count_is_none() -> None:
    """Cached None (no data) -> live call as before."""
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
            return httpx.Response(200, json={"result": []})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)
    inv = _inventory_with_target("com.target", record_count=None)
    result = asyncio.run(
        compute_impact(
            inv,
            "com.target",
            url="https://x.example",
            token="t",
            transport=transport,
        )
    )
    assert len(stats_calls) == 1
    assert result.counts_available is True
```

The `_plugin` and `_inventory` helpers must already exist in this test file from D2. If `_plugin` doesn't already accept the impact-only `PluginInfo` shape, copy it from `tests/test_plugins_orphans.py` (D3 version). If both exist with different shapes, prefer the existing D2 helper to keep the file consistent.

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py -v -k "skips_live or calls_live_when_cached_record"`

Expected: first test fails (live call IS made when cached==0); others pass already.

- [ ] **Step 3: Modify `compute_impact` in `src/nexus/plugins/impact.py`**

Replace the body of `compute_impact` (lines 170-211 currently):

```python
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
        PluginImpact with reverse-deps and record counts.

        Fast path: if the target's cached ``record_count == 0`` (from
        a refresh-time fan-out), skips the live aggregate call entirely
        and returns ``record_counts=()`` with ``counts_available=True``.

        Otherwise (cached > 0 or None): performs the live aggregate
        call for the per-table breakdown. If the call fails,
        ``counts_available=False`` and ``record_counts=()``.

    Raises:
        PluginImpactError: If ``target`` is not present in the inventory.
    """
    deps = reverse_dependencies(inventory, target)
    target_info = next(p for p in inventory.plugins if p.plugin_id == target)

    # Fast-path: cached zero means no records exist; skip live call.
    if target_info.record_count == 0:
        return PluginImpact(
            target_plugin_id=target,
            target_name=target_info.name,
            reverse_deps=deps,
            record_counts=(),
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

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_impact.py -v`

Expected: all impact tests pass (existing + 3 new).

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/plugins/impact.py tests/test_plugins_impact.py
.venv/Scripts/pyright src/nexus/plugins/impact.py tests/test_plugins_impact.py
```

```bash
git add src/nexus/plugins/impact.py tests/test_plugins_impact.py
git commit -m "perf(plugins): compute_impact skips live call when cached record_count==0

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: `--no-counts` opt-out on refresh

**Files:**
- Modify: `src/nexus/plugins/scanner.py` (`PluginScanner.scan` gets `capture_counts` kwarg)
- Modify: `src/nexus/cli.py` (`instance_refresh` gets `--no-counts` flag)
- Modify: `tests/test_plugins_scanner.py`
- Modify: `tests/test_cli_instance.py`

- [ ] **Step 1: Write failing scanner test**

Append to `tests/test_plugins_scanner.py`:

```python
def test_scan_skips_count_fan_out_when_capture_counts_false() -> None:
    """capture_counts=False -> no stats requests; all record_count is None."""
    stats_calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            stats_calls.append(str(req.url))
            return httpx.Response(200, json={"result": []})
        if "v_plugin" in req.url.path:
            return httpx.Response(200, json={"result": V_PLUGIN_ROWS})
        if "sys_store_app" in req.url.path:
            return httpx.Response(200, json={"result": SYS_STORE_APP_ROWS})
        return httpx.Response(404, json={"result": []})

    transport = httpx.MockTransport(handler)

    async def _run() -> PluginInventory:
        scanner = PluginScanner(transport=transport)
        return await scanner.scan(
            url="https://x.example",
            token="t",
            sn_version="Xanadu",
            capture_counts=False,
        )

    inv = asyncio.run(_run())
    assert stats_calls == []
    assert all(p.record_count is None for p in inv.plugins)
```

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_scanner.py -v -k "capture_counts_false"`

Expected: TypeError -- `scan()` doesn't accept `capture_counts` yet.

- [ ] **Step 3: Modify `PluginScanner.scan` in `src/nexus/plugins/scanner.py`**

Replace the `scan()` signature and body (around lines 44-95):

```python
async def scan(
    self,
    url: str,
    token: str,
    sn_version: str,
    *,
    capture_counts: bool = True,
) -> PluginInventory:
    """Capture the full plugin inventory.

    Args:
        url: Instance base URL.
        token: OAuth bearer token.
        sn_version: SN release name copied verbatim into the inventory.
        capture_counts: When True (default), fan out one
            ``/api/now/stats/sys_metadata`` call per plugin to
            populate ``PluginInfo.record_count``. When False, skip
            the fan-out -- every plugin's ``record_count`` stays at
            ``None``. Used by ``nexus instance refresh --no-counts``
            for faster refreshes when orphan detection is not needed.

    Returns:
        PluginInventory with deduped plugins from both tables.

    Raises:
        PluginScanError: When both source tables return non-200 responses.
    """
    async with httpx.AsyncClient(
        base_url=url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=30.0,
        transport=self._transport,
    ) as client:
        (v_rows, v_err), (s_rows, s_err) = await asyncio.gather(
            self._fetch(client, "v_plugin", _V_PLUGIN_FIELDS),
            self._fetch(client, "sys_store_app", _STORE_FIELDS),
        )

        if v_err is not None and s_err is not None:
            raise PluginScanError(s_err[0], s_err[1])

        by_id: dict[str, PluginInfo] = {}
        for row in v_rows:
            info = self._from_v_plugin(row)
            by_id[info.plugin_id] = info
        for row in s_rows:
            info = self._from_store(row)
            by_id[info.plugin_id] = info

        if capture_counts:
            counts = await _fetch_counts(client, tuple(by_id.keys()))
            by_id = {
                pid: info.model_copy(update={"record_count": counts.get(pid)})
                for pid, info in by_id.items()
            }

    return PluginInventory(
        captured_at=datetime.now(UTC),
        sn_version=sn_version,
        plugins=tuple(by_id.values()),
    )
```

- [ ] **Step 4: Run scanner test; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_scanner.py -v`

Expected: all scanner tests pass.

- [ ] **Step 5: Write failing CLI test**

Append to `tests/test_cli_instance.py`. First read the file's existing import block, helpers (`_meta`, `_seed`, `runner` fixture if present) -- if absent, use the same pattern as `tests/test_cli_plugins_updates.py`.

```python
def test_instance_refresh_no_counts_flag_skips_count_capture(
    runner: CliRunner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`nexus instance refresh --no-counts` calls scanner with capture_counts=False."""
    _seed(tmp_path, "prod", None)
    runner.invoke(app, ["instance", "use", "prod"])

    captured_kwargs: dict[str, object] = {}

    class _RecordingScanner:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        async def scan(
            self,
            url: str,
            token: str,
            sn_version: str,
            *,
            capture_counts: bool = True,
        ) -> PluginInventory:
            captured_kwargs["capture_counts"] = capture_counts
            return PluginInventory(
                captured_at=datetime.now(UTC),
                sn_version=sn_version,
                plugins=(),
            )

    # Patch BOTH PluginScanner and InstanceScanner so the refresh succeeds without
    # making any real HTTP calls; replace the OAuth helper too.
    monkeypatch.setattr("nexus.cli.PluginScanner", _RecordingScanner)
    # ... (real test will need to also stub InstanceScanner + _acquire_token; mirror
    # the pattern in tests/test_cli_instance.py's existing refresh tests if any)
    # If the existing refresh tests already stub these, follow their pattern verbatim.

    result = runner.invoke(app, ["instance", "refresh", "prod", "--no-counts"])
    assert result.exit_code == 0
    assert captured_kwargs.get("capture_counts") is False
```

IMPORTANT for the implementer: `tests/test_cli_instance.py` already exists and contains refresh tests. INSPECT IT FIRST to learn the exact pattern for stubbing `_acquire_token` and `InstanceScanner`. The test sketch above is illustrative; the real test must follow the file's conventions for fixture reuse. If the file's existing refresh tests use a different scanner-stubbing approach, follow that approach.

- [ ] **Step 6: Run CLI test; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_cli_instance.py -v -k "no_counts_flag"`

Expected: failure -- `--no-counts` flag is not recognized.

- [ ] **Step 7: Modify `instance_refresh` in `src/nexus/cli.py`**

Add the flag (around line 893-894):

```python
@instance_app.command("refresh")
def instance_refresh(
    profile: str = typer.Argument(""),
    no_counts: Annotated[
        bool,
        typer.Option(
            "--no-counts",
            help="Skip per-plugin record-count capture for a faster refresh.",
        ),
    ] = False,
) -> None:
    """Pull a fresh artifact snapshot from the instance."""
    registry, meta, token, new_expiry = _acquire_token(profile)
    profile = meta.profile

    console.print(Notice.info(f"Capturing snapshot from {profile!r}..."))

    async def _run() -> tuple[InstanceSnapshot, PluginInventory | None]:
        scanner = InstanceScanner()
        plugin_scanner = PluginScanner()
        snapshot_task = scanner.scan(meta.url, token, meta.sn_version)
        plugin_task = plugin_scanner.scan(
            meta.url,
            token,
            meta.sn_version,
            capture_counts=not no_counts,
        )
        results = await asyncio.gather(snapshot_task, plugin_task, return_exceptions=True)
        snap_result, plugin_result = results
        if isinstance(snap_result, BaseException):
            raise snap_result
        if isinstance(plugin_result, PluginScanError):
            err_console.print(Notice.warn(f"Plugin scan failed: {plugin_result}"))
            return snap_result, None
        if isinstance(plugin_result, BaseException):
            raise plugin_result
        return snap_result, plugin_result

    # ... (rest of the function body unchanged from current state)
```

The diff is: add `no_counts` parameter; add `capture_counts=not no_counts` to the `plugin_scanner.scan(...)` call. Everything else in `instance_refresh` is untouched.

- [ ] **Step 8: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_cli_instance.py tests/test_plugins_scanner.py -v`

- [ ] **Step 9: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/cli.py src/nexus/plugins/scanner.py tests/test_cli_instance.py tests/test_plugins_scanner.py
.venv/Scripts/pyright src/nexus/cli.py src/nexus/plugins/scanner.py tests/test_cli_instance.py tests/test_plugins_scanner.py
```

```bash
git add src/nexus/cli.py src/nexus/plugins/scanner.py tests/test_cli_instance.py tests/test_plugins_scanner.py
git commit -m "feat(cli): nexus instance refresh --no-counts opt-out flag

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: `--format text|json` infrastructure

This task adds the shared `_validate_format` + `_emit_json` helpers and the two inline wrapper models (`_OrphansReport`, `_UpdatesReport`). Per-command wiring lands in Tasks 6-12.

**Files:**
- Modify: `src/nexus/cli.py`

- [ ] **Step 1: Add helpers + wrappers near the top of cli.py**

Locate the existing constant section (around lines 109-117 where `_PLUGINS_HELP` lives) and add below it:

```python
_FORMATS = ("text", "json")


def _validate_format(value: str) -> None:
    """Reject unknown ``--format`` values with a clear error.

    Args:
        value: User-provided format string.

    Raises:
        typer.Exit: With code 1 on unknown values, after printing
            a Notice.error to the console.
    """
    if value not in _FORMATS:
        console.print(Notice.error(f"Unknown --format: {value}"))
        raise typer.Exit(1)


def _emit_json(model: BaseModel) -> None:
    """Print model JSON serialization to stdout, one line.

    Uses ``model.model_dump_json()`` (not Rich's print_json) so the
    output is single-line and CI-script-friendly.

    Args:
        model: Any Pydantic model to serialize.
    """
    print(model.model_dump_json())


class _OrphansReport(BaseModel):
    """Inline wrapper for JSON output of nexus plugins orphans.

    Attributes:
        candidates: Plugins identified as orphan candidates.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    candidates: tuple[PluginInfo, ...]


class _UpdatesReport(BaseModel):
    """Inline wrapper for JSON output of nexus plugins updates.

    Attributes:
        updates: Plugins with newer versions available.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    updates: tuple[PluginInfo, ...]
```

You will need to add `from pydantic import BaseModel, ConfigDict` to the existing import block at the top of cli.py if not already present (search for `from pydantic` -- it may already exist for other reasons).

- [ ] **Step 2: Verify**

```
.venv/Scripts/ruff check src/nexus/cli.py
.venv/Scripts/pyright src/nexus/cli.py
```

No new test in this task -- the helpers are exercised by Tasks 6-12. Both checks should report 0 errors.

- [ ] **Step 3: Commit**

```bash
git add src/nexus/cli.py
git commit -m "feat(cli): add _validate_format, _emit_json, and JSON wrapper models

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `--format` on `nexus plugins list` and `info`

**Files:**
- Modify: `src/nexus/cli.py` (`plugins_list` and `plugins_info` commands)
- Modify: `tests/test_cli_plugins.py` (or wherever list/info tests live -- inspect first)

- [ ] **Step 1: Identify the test file**

```
grep -rn "test_list_renders\|test_info_renders\|plugins.*list\|plugins.*info" tests/test_cli_plugins*.py | head -10
```

Use the resulting file. Likely `tests/test_cli_plugins.py`.

- [ ] **Step 2: Write failing tests (4 total: 2 per command)**

```python
def test_list_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "list", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert "plugins" in payload  # PluginInventory shape
    assert any(p["plugin_id"] == "com.x" for p in payload["plugins"])


def test_list_errors_on_unknown_format_value(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "list", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output


def test_info_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "info", "com.x", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert payload["plugin_id"] == "com.x"


def test_info_errors_on_unknown_format_value(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "info", "com.x", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output
```

Add `import json` to the test file's module-top imports if missing.

The `result.output.strip().split("\n")[-1]` pattern extracts the LAST line of output -- Rich may have printed banners/Hints earlier; the JSON is always the final stdout line written by `print()`.

- [ ] **Step 3: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_cli_plugins.py -v -k "emits_json or errors_on_unknown_format"`

- [ ] **Step 4: Modify `plugins_list` and `plugins_info` in `src/nexus/cli.py`**

Both commands gain an `output_format` parameter and a JSON branch. The signature additions (for `plugins_list`):

```python
output_format: Annotated[
    str,
    typer.Option("--format", help="Output format: text | json (default: text)"),
] = "text",
```

And early in the function body (after the inventory is loaded):

```python
_validate_format(output_format)
if output_format == "json":
    _emit_json(inventory)  # PluginInventory already wraps plugins
    return
```

For `plugins_info`, the JSON branch emits the single matching PluginInfo:

```python
_validate_format(output_format)
matching = next((p for p in inventory.plugins if p.plugin_id == plugin_id), None)
if matching is None:
    console.print(Notice.error(f"Plugin not found: {plugin_id}"))
    raise typer.Exit(1)
if output_format == "json":
    _emit_json(matching)
    return
```

Inspect the existing command bodies first to find the right insertion points -- the JSON branch should fire AFTER input validation (so unknown plugin still errors via the existing path) but BEFORE the Rich rendering.

- [ ] **Step 5: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_cli_plugins.py -v`

- [ ] **Step 6: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/cli.py tests/test_cli_plugins.py
.venv/Scripts/pyright src/nexus/cli.py tests/test_cli_plugins.py
```

```bash
git add src/nexus/cli.py tests/test_cli_plugins.py
git commit -m "feat(cli): --format json on nexus plugins list and info

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `--format` on `nexus plugins diff`

**Files:**
- Modify: `src/nexus/cli.py` (`plugins_diff` command)
- Modify: `tests/test_cli_plugins_diff.py`

- [ ] **Step 1: Append failing tests**

```python
def test_diff_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    # Seed two profiles with diverging plugins. Reuse the file's existing
    # _seed_pair helper if present; otherwise mirror the diff test pattern.
    _seed(tmp_path, "prod", (_info("com.x", version="1.0"),))
    _seed(tmp_path, "dev", (_info("com.x", version="2.0"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "diff", "prod", "dev", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert "entries" in payload


def test_diff_errors_on_unknown_format_value(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.x"),))
    _seed(tmp_path, "dev", (_info("com.x"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "diff", "prod", "dev", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output
```

The test must use whatever helpers `tests/test_cli_plugins_diff.py` already defines for seeding two profiles. If they exist with different names, use those.

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_diff.py -v -k "emits_json or errors_on_unknown_format"`

- [ ] **Step 3: Modify `plugins_diff` in cli.py**

Add the `output_format` parameter (same shape as Task 6) and a JSON branch:

```python
_validate_format(output_format)
# ... after compute_diff produces the PluginDiff ...
if output_format == "json":
    _emit_json(diff)  # PluginDiff has entries: tuple[PluginDiffEntry, ...]
    return
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_diff.py -v`

- [ ] **Step 5: Verify + commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_diff.py
git commit -m "feat(cli): --format json on nexus plugins diff

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: `--format` on `nexus plugins advisories`

**Files:**
- Modify: `src/nexus/cli.py` (`plugins_advisories` command)
- Modify: `tests/test_cli_plugins_advisories.py`

- [ ] **Step 1: Append failing tests**

```python
def test_advisories_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert "findings" in payload


def test_advisories_errors_on_unknown_format_value(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.x", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output
```

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_advisories.py -v -k "emits_json or errors_on_unknown_format"`

- [ ] **Step 3: Modify `plugins_advisories`**

Add `output_format` parameter, validate it early, and emit JSON when set. The JSON object is the filtered `AdvisorySet`:

```python
_validate_format(output_format)
# ... after filtering findings by --type and --severity ...
if output_format == "json":
    _emit_json(AdvisorySet(findings=findings))
    return
```

`AdvisorySet` is already imported in cli.py from D1.

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_advisories.py
git commit -m "feat(cli): --format json on nexus plugins advisories

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: `--format` on `nexus plugins updates`

**Files:**
- Modify: `src/nexus/cli.py` (`plugins_updates`)
- Modify: `tests/test_cli_plugins_updates.py`

- [ ] **Step 1: Append failing tests**

```python
def test_updates_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert "updates" in payload
    assert payload["updates"][0]["plugin_id"] == "com.acme.helper"


def test_updates_errors_on_unknown_format_value(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.acme.helper", version="3.0.0", latest_version="3.1.0"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "updates", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output
```

- [ ] **Step 2: Run; expect FAIL**

- [ ] **Step 3: Modify `plugins_updates`**

Add `output_format` parameter; emit JSON via the inline `_UpdatesReport` wrapper:

```python
_validate_format(output_format)
# ... after plugins_with_updates(inventory) ...
if output_format == "json":
    _emit_json(_UpdatesReport(updates=tuple(pending)))
    return
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_updates.py
git commit -m "feat(cli): --format json on nexus plugins updates

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: `--format` on `nexus plugins impact`

**Files:**
- Modify: `src/nexus/cli.py` (`plugins_impact`)
- Modify: `tests/test_cli_plugins_impact.py`

- [ ] **Step 1: Append failing tests**

```python
def test_impact_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.target"),
            _info("com.dep", depends_on=("com.target",)),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(
        app, ["plugins", "impact", "com.target", "--format", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert payload["target_plugin_id"] == "com.target"
    assert "reverse_deps" in payload


def test_impact_errors_on_unknown_format_value(
    runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path, "prod", (_info("com.target"),))
    runner.invoke(app, ["instance", "use", "prod"])
    _patch_token_and_stats(monkeypatch)
    result = runner.invoke(
        app, ["plugins", "impact", "com.target", "--format", "yaml"]
    )
    assert result.exit_code == 1
    assert "Unknown --format" in result.output
```

- [ ] **Step 2: Run; expect FAIL**

- [ ] **Step 3: Modify `plugins_impact`**

Add `output_format` parameter; emit `PluginImpact` directly:

```python
_validate_format(output_format)
# ... after compute_impact returns ...
if output_format == "json":
    _emit_json(impact)
    return
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_impact.py
git commit -m "feat(cli): --format json on nexus plugins impact

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: `--format` on `nexus plugins orphans`

**Files:**
- Modify: `src/nexus/cli.py` (`plugins_orphans`)
- Modify: `tests/test_cli_plugins_orphans.py`

- [ ] **Step 1: Append failing tests**

```python
def test_orphans_emits_json_when_format_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.lonely", record_count=0),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output.strip().split("\n")[-1])
    assert "candidates" in payload
    assert payload["candidates"][0]["plugin_id"] == "com.lonely"


def test_orphans_errors_on_unknown_format_value(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.x", record_count=0),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans", "--format", "yaml"])
    assert result.exit_code == 1
    assert "Unknown --format" in result.output
```

- [ ] **Step 2: Run; expect FAIL**

- [ ] **Step 3: Modify `plugins_orphans`**

Add `output_format` parameter; emit via `_OrphansReport`:

```python
_validate_format(output_format)
# ... after orphan_candidates(inventory) + --state filter ...
if output_format == "json":
    _emit_json(_OrphansReport(candidates=tuple(candidates)))
    return
```

- [ ] **Step 4: Run; expect PASS**

- [ ] **Step 5: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_orphans.py
git commit -m "feat(cli): --format json on nexus plugins orphans

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: `--strict` on `nexus plugins advisories`

**Files:**
- Modify: `src/nexus/cli.py` (`plugins_advisories`)
- Modify: `tests/test_cli_plugins_advisories.py`

- [ ] **Step 1: Append failing tests**

```python
def test_advisories_strict_exits_1_when_findings_present(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories", "--strict"])
    assert result.exit_code == 1


def test_advisories_strict_exits_0_when_no_findings(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.unaffected", vendor="ServiceNow"),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "advisories", "--strict"])
    assert result.exit_code == 0
    assert "No advisories found" in result.output


def test_advisories_strict_respects_severity_filter(
    runner: CliRunner, tmp_path: Path
) -> None:
    """--strict + --severity that filters out all findings exits 0."""
    _seed(
        tmp_path,
        "prod",
        # ESS is HIGH severity by default; --severity critical filters it out.
        (_info("com.snc.ess", version="1.0", vendor="ServiceNow"),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(
        app, ["plugins", "advisories", "--strict", "--severity", "critical"]
    )
    assert result.exit_code == 0
```

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_advisories.py -v -k "strict"`

- [ ] **Step 3: Modify `plugins_advisories`**

Add the `strict` parameter:

```python
strict: Annotated[
    bool,
    typer.Option(
        "--strict",
        help="Exit with code 1 if any findings remain after filters.",
    ),
] = False,
```

And the exit logic at the END of the command body, AFTER rendering (so the user sees the findings before the non-zero exit):

```python
# ... existing logic: filter, render (text or json), trailing notice ...

if strict and findings:
    raise typer.Exit(1)
```

`findings` is the filtered tuple already in scope from earlier in the function.

NOTE on the `--format json` interaction: when both `--strict` and `--format json` are set AND findings exist, the JSON is emitted to stdout via `_emit_json(...)` then `typer.Exit(1)` fires. The JSON output reaches stdout cleanly because `_emit_json` uses `print()` (line-buffered) which flushes before the exception propagates.

The "No advisories found" early-return path skips both the strict-exit check and the rendering. With `--strict` and zero findings, exit is 0 because we never reach the `if strict and findings:` line.

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_advisories.py -v`

- [ ] **Step 5: Verify + commit**

```
.venv/Scripts/ruff check src/nexus/cli.py tests/test_cli_plugins_advisories.py
.venv/Scripts/pyright src/nexus/cli.py tests/test_cli_plugins_advisories.py
```

```bash
git add src/nexus/cli.py tests/test_cli_plugins_advisories.py
git commit -m "feat(cli): nexus plugins advisories --strict (exit 1 on findings)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Black + ratchet + PR

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Black**

`.venv/Scripts/black src/nexus/plugins/ src/nexus/cli.py tests/test_plugins_scanner.py tests/test_plugins_impact.py tests/test_cli_instance.py tests/test_cli_plugins*.py`

- [ ] **Step 2: Full quality gate**

```
.venv/Scripts/ruff check src tests            # 0 violations
.venv/Scripts/mypy src/nexus/                 # 0 errors
.venv/Scripts/pyright src/nexus/              # 0 errors
.venv/Scripts/python -m pytest --no-cov --ignore=tests/test_updater_runner.py
# Expected: all new tests pass; 4 pre-existing failures unchanged
```

- [ ] **Step 3: Measure coverage**

```
.venv/Scripts/python -m pytest --ignore=tests/test_updater_runner.py --cov=nexus --cov-report=json --cov-fail-under=0
```

Extract numbers for:
- `src/nexus/cli.py`
- `src/nexus/plugins/impact.py`
- `src/nexus/plugins/scanner.py`

If `coverage.json` is tracked in the repo, restore it after measurement: `git checkout coverage.json`.

- [ ] **Step 4: Update `.ratchet.json`**

Update the three keys with the freshly measured values. Do not change unrelated keys.

```jsonc
{
  ...
  "modules": {
    ...
    "nexus.cli": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.impact": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.scanner": {"covered_lines": <new>, "total_lines": <new>},
    ...
  }
}
```

Ratchet rule: `covered_lines` must be >= the previous value for each module; `total_lines` reflects the new module size.

- [ ] **Step 5: Commit**

```bash
git add .ratchet.json src/nexus/plugins/ src/nexus/cli.py tests/
git commit -m "chore(plugins): black formatting + refresh ratchet for cleanups

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Push + open PR**

```bash
git push -u origin feat/plugins-cleanups
gh pr create --base main --title "feat(plugins): G cleanups (pagination, DRY, cached impact, --no-counts, --format json, --strict)" --body "$(cat <<'EOF'
## Summary
Six surgical cleanups noted while shipping sub-projects A-D3:

1. **Pagination loop** in PluginScanner._fetch (was sysparm_limit=200 with no loop, silently truncating >200 plugins).
2. **DRY**: extract `_fetch_scope_counts_with_client` shared by `impact.fetch_scope_record_counts` and `scanner._sum_scope_records`.
3. **Cached fast-path** in `compute_impact`: skip live REST call when target's cached `record_count == 0`.
4. **`nexus instance refresh --no-counts`** opt-out flag (skips the D3 fan-out for faster refreshes).
5. (Skipped -- drift detection is sub-project H.)
6. **`--format text|json`** across 7 commands: list, info, diff, advisories, impact, orphans, updates. JSON via `model.model_dump_json()` for CI consumption.
7. **`--strict`** flag on `nexus plugins advisories` -- exit 1 when findings remain after filters (matches ruff/mypy/black convention).

Sub-project G of plugin management.

Spec: docs/superpowers/specs/2026-05-12-plugin-cleanups-design.md
Plan: docs/superpowers/plans/2026-05-12-plugin-cleanups.md

## Test plan
- [x] 3 new tests in `tests/test_plugins_scanner.py` (pagination + capture_counts)
- [x] 4 new tests in `tests/test_plugins_impact.py` (with_client helper + cached fast-path)
- [x] 1 new test in `tests/test_cli_instance.py` (--no-counts)
- [x] 14 new tests across `tests/test_cli_plugins*.py` (--format on 7 commands)
- [x] 3 new tests in `tests/test_cli_plugins_advisories.py` (--strict)
- [x] Full suite green except 4 pre-existing failures
- [x] ruff / black / mypy strict / pyright strict clean

EOF
)"
```

---

## Self-Review Summary

**Spec coverage:**
- Item 1 (pagination loop + cap) -> Task 1
- Item 2 (DRY consolidation) -> Task 2
- Item 3 (cached fast-path) -> Task 3
- Item 4 (--no-counts flag) -> Task 4
- Item 5 (drift) -> explicitly deferred to sub-project H
- Item 6 (--format json) -> Tasks 5 (infrastructure) + 6/7/8/9/10/11 (7 commands)
- Item 7 (--strict) -> Task 12
- Quality gate + PR -> Task 13

All spec sections trace to a task.

**Placeholder scan:** No "TBD"/"TODO"/"etc." in the plan body. The `<new>` markers in Task 13's ratchet block are intentionally pinned to "measure then fill in" -- explicit instruction.

**Type consistency:** All function signatures consistent. `_fetch_scope_counts_with_client(client, plugin_id) -> tuple[ScopeRecordCount, ...]` defined in Task 2 matches usage in Task 2's scanner refactor and Task 3's compute_impact (indirectly via `fetch_scope_record_counts`). `_OrphansReport.candidates` and `_UpdatesReport.updates` field names consistent between Task 5 (definition) and Tasks 11/9 (usage). `--format` parameter is named `output_format` in all 7 commands.
