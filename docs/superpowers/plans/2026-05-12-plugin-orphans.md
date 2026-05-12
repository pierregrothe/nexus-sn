# Plugin Orphan Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `nexus plugins orphans`, a CLI command that surfaces plugins with no dependents AND no scope-owned records. Adds a refresh-time aggregate-API fan-out so per-plugin record counts live in `plugins.json`.

**Architecture:** Three steps. (1) Add `record_count: int | None = None` field to `PluginInfo`. (2) Extend `PluginScanner.scan()` with a bounded-concurrency aggregate-API fan-out that populates `record_count` for each plugin via `/api/now/stats/sys_metadata?sysparm_query=sys_scope.scope=<plugin_id>&sysparm_count=true&sysparm_group_by=sys_class_name`. (3) Add a pure `orphan_candidates(inventory) -> tuple[PluginInfo, ...]` function plus a CLI command that renders the result. Partial fan-out failures are tolerated -- per-plugin `record_count` becomes `None`, the rest of the refresh succeeds.

**Tech Stack:** Python 3.14, Pydantic v2 (frozen+strict+extra=forbid), `httpx.AsyncClient` + `httpx.MockTransport`, `asyncio.Semaphore` for concurrency cap, Typer, Rich.

**Branch:** `feat/plugins-orphans` (stacked on PR #15 -- `feat/plugins-impact`).

**Spec:** `docs/superpowers/specs/2026-05-12-plugin-orphans-design.md`

---

## File Map

**Create:**
- `src/nexus/plugins/orphans.py` -- `orphan_candidates` pure function
- `tests/test_plugins_orphans.py`
- `tests/test_cli_plugins_orphans.py`

**Modify:**
- `src/nexus/plugins/models.py` -- add `record_count: int | None = None` to PluginInfo
- `src/nexus/plugins/scanner.py` -- add `_ScopeRecordCountError`, `_sum_scope_records`, `_fetch_counts`; chain into `scan()`
- `src/nexus/plugins/__init__.py` -- re-export `orphan_candidates`
- `src/nexus/cli.py` -- new `orphans` subcommand + update `_PLUGINS_HELP`
- `tests/test_plugins_models.py` -- 3 new tests
- `tests/test_plugins_scanner.py` -- 3 new tests
- `.ratchet.json` -- new baselines + cli.py / scanner.py / models.py / init bumps

---

## Task 1: record_count field on PluginInfo

**Files:**
- Modify: `src/nexus/plugins/models.py` (PluginInfo class)
- Modify: `tests/test_plugins_models.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_models.py`:

```python
def test_plugin_info_accepts_record_count_field() -> None:
    info = PluginInfo(
        plugin_id="com.x",
        name="X",
        version="1.0",
        state="active",
        source="store",
        product_family="ITSM",
        depends_on=(),
        sys_id="abc",
        installed_at=None,
        record_count=42,
    )
    assert info.record_count == 42


def test_plugin_info_defaults_record_count_to_none() -> None:
    info = PluginInfo(
        plugin_id="com.x",
        name="X",
        version="1.0",
        state="active",
        source="store",
        product_family="ITSM",
        depends_on=(),
        sys_id="abc",
        installed_at=None,
    )
    assert info.record_count is None


def test_plugin_info_accepts_record_count_zero() -> None:
    info = PluginInfo(
        plugin_id="com.x",
        name="X",
        version="1.0",
        state="active",
        source="store",
        product_family="ITSM",
        depends_on=(),
        sys_id="abc",
        installed_at=None,
        record_count=0,
    )
    assert info.record_count == 0
```

`PluginInfo` is already imported in the test file.

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_models.py -v -k "record_count"`

Expected: Pydantic `extra="forbid"` error -- `record_count` is not a recognized field.

- [ ] **Step 3: Add `record_count` to PluginInfo**

In `src/nexus/plugins/models.py`, modify the `PluginInfo` class. Add `record_count: int | None = None` immediately after `vendor: str = ""`. Append to the docstring's Attributes block:

```python
class PluginInfo(BaseModel):
    """One plugin's static metadata on an instance.

    Attributes:
        plugin_id: Canonical SN plugin identifier (e.g. ``com.snc.incident``).
        name: Display name from sys_store_app.name or v_plugin.name.
        version: Currently installed version string.
        state: ``active`` if activated, ``inactive`` otherwise.
        source: Origin of the plugin record.
        product_family: Curated product family or ``Uncategorized``.
        depends_on: Direct plugin dependencies (no traversal at this layer).
        sys_id: SN record sys_id.
        installed_at: Activation timestamp; ``None`` if never activated.
        latest_version: The newest available version per ``sys_store_app``;
            ``None`` for v_plugin-only records (core SN plugins) and for
            store apps where the field is empty.
        vendor: Publisher name from ``sys_store_app.vendor``. Empty string
            for v_plugin-only records or when the field is absent.
        record_count: Total records in this plugin's scope as reported by
            ``sys_metadata`` aggregation. ``None`` when not captured (older
            snapshots, or a partial-fetch failure during scan). Used by
            orphan detection.
    """

    model_config = _FROZEN

    plugin_id: str
    name: str
    version: str
    state: Literal["active", "inactive"]
    source: Literal["servicenow", "store", "custom"]
    product_family: str
    depends_on: tuple[str, ...]
    sys_id: str
    installed_at: UtcDatetime | None
    latest_version: str | None = None
    vendor: str = ""
    record_count: int | None = None
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_models.py -v`

Expected: all model tests pass (23 minimum: 20 prior + 3 new).

- [ ] **Step 5: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/models.py tests/test_plugins_models.py
.venv/Scripts/pyright src/nexus/plugins/models.py tests/test_plugins_models.py
```

Both: 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/models.py tests/test_plugins_models.py
git commit -m "feat(plugins): add record_count field to PluginInfo

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: _ScopeRecordCountError + _sum_scope_records in scanner

**Files:**
- Modify: `src/nexus/plugins/scanner.py`
- Modify: `tests/test_plugins_scanner.py`

- [ ] **Step 1: Extend `_transport_for` in `tests/test_plugins_scanner.py` to also handle the stats endpoint**

Find the existing `_transport_for` helper (lines 20-37). Add a third branch to the handler:

```python
def _transport_for(
    v_plugin_status: int = 200,
    store_status: int = 200,
    v_plugin_rows: list[dict[str, object]] | None = None,
    store_rows: list[dict[str, object]] | None = None,
    stats_status: int = 200,
    stats_payload: dict[str, object] | None = None,
) -> httpx.MockTransport:
    """Build a transport that serves all three endpoints with the given rows/status."""
    v_rows = v_plugin_rows if v_plugin_rows is not None else V_PLUGIN_ROWS
    s_rows = store_rows if store_rows is not None else SYS_STORE_APP_ROWS
    body: dict[str, object] = (
        stats_payload if stats_payload is not None else {"result": []}
    )

    def handler(req: httpx.Request) -> httpx.Response:
        if "/api/now/stats/sys_metadata" in req.url.path:
            return httpx.Response(stats_status, json=body)
        if "v_plugin" in req.url.path:
            return httpx.Response(v_plugin_status, json={"result": v_rows})
        if "sys_store_app" in req.url.path:
            return httpx.Response(store_status, json={"result": s_rows})
        return httpx.Response(404, json={"result": []})

    return httpx.MockTransport(handler)
```

This extension is backwards-compatible: existing call sites without `stats_status`/`stats_payload` get the default empty `{"result": []}` response, which means `record_count` ends up `0` for every plugin in those tests. If any pre-existing test depends on `record_count` being `None`, the test will need updating in the same task. (None currently do; this is documented for awareness.)

- [ ] **Step 2: Write failing test for the helper internals**

Append to `tests/test_plugins_scanner.py`:

```python
from nexus.plugins.scanner import _ScopeRecordCountError, _sum_scope_records


def _stats_response(rows: list[dict[str, object]]) -> dict[str, object]:
    return {"result": rows}


def _stats_row(table: str, count: int) -> dict[str, object]:
    return {
        "stats": {"count": str(count)},
        "groupby_fields": [{"field": "sys_class_name", "value": table}],
    }


async def _run_sum(transport: httpx.MockTransport, plugin_id: str = "com.x") -> int:
    async with httpx.AsyncClient(
        base_url="https://x.example",
        headers={"Authorization": "Bearer t"},
        transport=transport,
    ) as client:
        return await _sum_scope_records(client, plugin_id)


def test_sum_scope_records_returns_total_across_tables() -> None:
    transport = _transport_for(
        stats_payload=_stats_response(
            [
                _stats_row("sys_script", 100),
                _stats_row("sys_business_rule", 25),
            ]
        ),
    )
    total = asyncio.run(_run_sum(transport))
    assert total == 125


def test_sum_scope_records_returns_zero_for_empty_result() -> None:
    transport = _transport_for(stats_payload=_stats_response([]))
    total = asyncio.run(_run_sum(transport))
    assert total == 0


def test_sum_scope_records_raises_on_non_200() -> None:
    transport = _transport_for(stats_status=403)
    with pytest.raises(_ScopeRecordCountError):
        asyncio.run(_run_sum(transport))


def test_sum_scope_records_raises_on_malformed_response() -> None:
    transport = _transport_for(stats_payload={"no_result_key": True})
    with pytest.raises(_ScopeRecordCountError):
        asyncio.run(_run_sum(transport))
```

NOTE: `_ScopeRecordCountError` and `_sum_scope_records` start with underscore, so they are conventionally private. They are still imported in tests because Python doesn't enforce privacy. The scanner does NOT export them in `__all__`.

- [ ] **Step 3: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_scanner.py -v -k "sum_scope_records"`

Expected: ImportError -- the names are not defined.

- [ ] **Step 4: Add `_ScopeRecordCountError` and `_sum_scope_records` to `src/nexus/plugins/scanner.py`**

Append at the END of the file (after `_parse_dt`):

```python
class _ScopeRecordCountError(Exception):
    """Raised when the per-scope aggregate REST call fails or is unparseable.

    Internal to ``scanner.py``. Caught by ``_fetch_counts`` to set
    a plugin's ``record_count`` to ``None`` without aborting the scan.
    """


async def _sum_scope_records(client: httpx.AsyncClient, plugin_id: str) -> int:
    """Return total records in ``plugin_id``'s scope via the Aggregate API.

    Sums per-``sys_class_name`` bucket counts from one
    ``/api/now/stats/sys_metadata`` call.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        plugin_id: Scope identifier (e.g. ``com.snc.incident``).

    Returns:
        Total record count across all sys_class_name buckets.

    Raises:
        _ScopeRecordCountError: On non-200 status or malformed response.
    """
    resp = await client.get(
        "/api/now/stats/sys_metadata",
        params={
            "sysparm_query": f"sys_scope.scope={plugin_id}",
            "sysparm_count": "true",
            "sysparm_group_by": "sys_class_name",
        },
    )
    if resp.status_code != 200:
        raise _ScopeRecordCountError(f"HTTP {resp.status_code}")
    try:
        rows = resp.json()["result"]
    except (KeyError, ValueError) as exc:
        raise _ScopeRecordCountError(f"malformed response: {exc}") from exc
    total = 0
    for row in rows:
        try:
            total += int(row["stats"]["count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise _ScopeRecordCountError(f"bad row: {exc}") from exc
    return total
```

Do NOT add `_ScopeRecordCountError` or `_sum_scope_records` to `__all__` -- they are private. `__all__` stays `["PluginScanner"]`.

- [ ] **Step 5: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_scanner.py -v -k "sum_scope_records"`

Expected: 4 PASS.

- [ ] **Step 6: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
.venv/Scripts/pyright src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
```

- [ ] **Step 7: Commit**

```bash
git add src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
git commit -m "feat(plugins): add _sum_scope_records helper for orphan detection

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: _fetch_counts with bounded concurrency

**Files:**
- Modify: `src/nexus/plugins/scanner.py`
- Modify: `tests/test_plugins_scanner.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_scanner.py`:

```python
from nexus.plugins.scanner import _fetch_counts


def test_fetch_counts_returns_count_per_plugin() -> None:
    transport = _transport_for(
        stats_payload=_stats_response([_stats_row("sys_script", 7)]),
    )

    async def _run() -> dict[str, int | None]:
        async with httpx.AsyncClient(
            base_url="https://x.example",
            headers={"Authorization": "Bearer t"},
            transport=transport,
        ) as client:
            return await _fetch_counts(client, ("com.a", "com.b"))

    counts = asyncio.run(_run())
    assert counts == {"com.a": 7, "com.b": 7}


def test_fetch_counts_marks_failed_plugin_as_none() -> None:
    transport = _transport_for(stats_status=500)

    async def _run() -> dict[str, int | None]:
        async with httpx.AsyncClient(
            base_url="https://x.example",
            headers={"Authorization": "Bearer t"},
            transport=transport,
        ) as client:
            return await _fetch_counts(client, ("com.a", "com.b"))

    counts = asyncio.run(_run())
    assert counts == {"com.a": None, "com.b": None}


def test_fetch_counts_caps_concurrent_calls_at_max_concurrency() -> None:
    in_flight = {"current": 0, "max": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        in_flight["current"] += 1
        if in_flight["current"] > in_flight["max"]:
            in_flight["max"] = in_flight["current"]
        try:
            return httpx.Response(200, json={"result": []})
        finally:
            in_flight["current"] -= 1

    transport = httpx.MockTransport(handler)

    async def _run() -> None:
        async with httpx.AsyncClient(
            base_url="https://x.example",
            headers={"Authorization": "Bearer t"},
            transport=transport,
        ) as client:
            ids = tuple(f"com.p{i}" for i in range(64))
            await _fetch_counts(client, ids, max_concurrency=4)

    asyncio.run(_run())
    assert in_flight["max"] <= 4
```

Notes:
- The concurrency-cap test passes `max_concurrency=4` (not the production default 16) so the bound is easier to verify with a small number of plugins.
- The httpx.MockTransport handler runs synchronously per request, so observed concurrency depends on how the async client/transport interleaves coroutines. With proper Semaphore-gating, max in-flight should never exceed the cap.

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_scanner.py -v -k "fetch_counts"`

- [ ] **Step 3: Add `_fetch_counts` to `src/nexus/plugins/scanner.py`**

Append at the END of the file:

```python
_DEFAULT_COUNTS_CONCURRENCY = 16


async def _fetch_counts(
    client: httpx.AsyncClient,
    plugin_ids: tuple[str, ...],
    *,
    max_concurrency: int = _DEFAULT_COUNTS_CONCURRENCY,
) -> dict[str, int | None]:
    """Fan out aggregate-API calls for each plugin under a concurrency cap.

    Args:
        client: Open httpx.AsyncClient bound to the instance URL.
        plugin_ids: Plugins to fetch counts for.
        max_concurrency: Maximum number of in-flight stats calls.

    Returns:
        ``plugin_id -> total record count`` mapping. Per-plugin failures
        surface as ``None`` so the whole refresh can succeed with
        partial data.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _one(pid: str) -> tuple[str, int | None]:
        async with semaphore:
            try:
                total = await _sum_scope_records(client, pid)
            except _ScopeRecordCountError as exc:
                log.warning("scan: count fetch failed for %s -- %s", pid, exc)
                return pid, None
            return pid, total

    results = await asyncio.gather(*(_one(pid) for pid in plugin_ids))
    return dict(results)
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_scanner.py -v -k "fetch_counts"`

Expected: 3 PASS.

- [ ] **Step 5: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
.venv/Scripts/pyright src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
```

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
git commit -m "feat(plugins): add _fetch_counts with bounded concurrency

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Chain _fetch_counts into PluginScanner.scan()

**Files:**
- Modify: `src/nexus/plugins/scanner.py`
- Modify: `tests/test_plugins_scanner.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plugins_scanner.py`:

```python
def test_scan_populates_record_count_from_aggregate_api() -> None:
    transport = _transport_for(
        stats_payload=_stats_response([_stats_row("sys_script", 42)]),
    )
    inv = asyncio.run(_scan(transport))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    assert incident.record_count == 42


def test_scan_sets_record_count_none_when_aggregate_call_fails() -> None:
    transport = _transport_for(stats_status=500)
    inv = asyncio.run(_scan(transport))
    # Every plugin's count fetch fails -> all None.
    assert all(p.record_count is None for p in inv.plugins)


def test_scan_keeps_other_fields_intact_after_count_capture() -> None:
    transport = _transport_for(
        stats_payload=_stats_response([_stats_row("sys_script", 5)]),
    )
    inv = asyncio.run(_scan(transport))
    incident = next(p for p in inv.plugins if p.plugin_id == "com.snc.incident")
    # Spot-check that adding record_count did not disturb other fields.
    assert incident.state == "active"
    assert incident.source == "servicenow"
    assert incident.version == "1.2.3"
```

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_scanner.py -v -k "record_count"`

Expected: `record_count` is `None` for every plugin (the field defaults to None; scan() hasn't been wired yet).

- [ ] **Step 3: Modify `PluginScanner.scan()` in `src/nexus/plugins/scanner.py`**

The current `scan()` body (lines 44-85) returns the inventory directly. Insert a counts-fan-out step BEFORE the final return, inside the same `async with httpx.AsyncClient(...)` block so the client is reused for stats calls:

```python
async def scan(self, url: str, token: str, sn_version: str) -> PluginInventory:
    """Capture the full plugin inventory.

    Args:
        url: Instance base URL.
        token: OAuth bearer token.
        sn_version: SN release name copied verbatim into the inventory.

    Returns:
        PluginInventory with deduped plugins from both tables. Each
        plugin's ``record_count`` is populated via a per-scope
        aggregate-API call; per-plugin fetch failures leave
        ``record_count`` at ``None`` without aborting the scan.

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
            # sys_store_app wins on conflict because it carries vendor.
            by_id[info.plugin_id] = info

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

The two changes vs the existing body:
1. The `async with httpx.AsyncClient(...)` block now extends through the counts capture so the same client is reused.
2. Two new lines: the `counts = await _fetch_counts(...)` call and the `by_id = {...}` rebuild that overlays `record_count` on each `PluginInfo`.

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_scanner.py -v`

Expected: all scanner tests pass.

NOTE on existing scanner tests: any test that does NOT pass `stats_payload` to `_transport_for` now exercises the stats endpoint and gets the default empty `{"result": []}` response, which means every plugin in those tests will have `record_count == 0`. If any existing assertion does `assert p.record_count is None`, that test now fails. Re-run the full file and adjust any such test by passing `stats_payload=None` is the old behavior; if needed, add a new helper variant or update the assertion. Scan the diff carefully.

If a previously-passing test breaks, the fix is one of:
- Update the assertion if it was relying on the default
- Pass an explicit `stats_payload` to match the new expectation

- [ ] **Step 5: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
.venv/Scripts/pyright src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
```

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/scanner.py tests/test_plugins_scanner.py
git commit -m "feat(plugins): scanner populates record_count via aggregate-API fan-out

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: orphan_candidates pure function

**Files:**
- Create: `src/nexus/plugins/orphans.py`
- Create: `tests/test_plugins_orphans.py`

- [ ] **Step 1: Create `tests/test_plugins_orphans.py` with header + failing tests**

```python
# tests/test_plugins_orphans.py
# Tests for the plugin orphan detection layer.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus.plugins.orphans.orphan_candidates."""

from datetime import UTC, datetime

from nexus.plugins.models import PluginInfo, PluginInventory
from nexus.plugins.orphans import orphan_candidates

__all__: list[str] = []


def _plugin(
    plugin_id: str,
    *,
    depends_on: tuple[str, ...] = (),
    state: str = "active",
    record_count: int | None = None,
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
            "record_count": record_count,
        }
    )


def _inventory(*plugins: PluginInfo) -> PluginInventory:
    return PluginInventory(
        captured_at=datetime(2026, 5, 12, tzinfo=UTC),
        sn_version="Washington",
        plugins=plugins,
    )


def test_orphan_candidates_returns_plugin_with_zero_deps_and_zero_records() -> None:
    inv = _inventory(_plugin("com.lonely", record_count=0))
    result = orphan_candidates(inv)
    assert len(result) == 1
    assert result[0].plugin_id == "com.lonely"


def test_orphan_candidates_excludes_plugin_with_dependents() -> None:
    inv = _inventory(
        _plugin("com.target", record_count=0),
        _plugin("com.consumer", depends_on=("com.target",), record_count=0),
    )
    result = orphan_candidates(inv)
    # com.target has a dependent so it's excluded; com.consumer has 0 deps + 0 records so IT is an orphan.
    assert [p.plugin_id for p in result] == ["com.consumer"]


def test_orphan_candidates_excludes_plugin_with_records() -> None:
    inv = _inventory(_plugin("com.busy", record_count=42))
    assert orphan_candidates(inv) == ()


def test_orphan_candidates_excludes_plugin_with_record_count_none() -> None:
    inv = _inventory(_plugin("com.unknown", record_count=None))
    assert orphan_candidates(inv) == ()


def test_orphan_candidates_includes_inactive_plugins() -> None:
    inv = _inventory(
        _plugin("com.dead", state="inactive", record_count=0),
    )
    assert orphan_candidates(inv)[0].state == "inactive"


def test_orphan_candidates_excludes_plugin_in_its_own_depends_on() -> None:
    inv = _inventory(
        _plugin("com.loop", depends_on=("com.loop",), record_count=0),
    )
    assert orphan_candidates(inv) == ()


def test_orphan_candidates_sorts_by_state_then_plugin_id() -> None:
    inv = _inventory(
        _plugin("com.b", state="inactive", record_count=0),
        _plugin("com.a", state="inactive", record_count=0),
        _plugin("com.z", state="active", record_count=0),
    )
    result = orphan_candidates(inv)
    assert [p.plugin_id for p in result] == ["com.z", "com.a", "com.b"]


def test_orphan_candidates_returns_empty_tuple_when_no_candidates() -> None:
    inv = _inventory(_plugin("com.busy", record_count=100))
    assert orphan_candidates(inv) == ()
```

- [ ] **Step 2: Run; expect FAIL (ImportError)**

`.venv/Scripts/python -m pytest tests/test_plugins_orphans.py -v`

- [ ] **Step 3: Create `src/nexus/plugins/orphans.py`**

```python
# src/nexus/plugins/orphans.py
# Orphan plugin detection over a captured inventory.
# Author: Pierre Grothe
# Date: 2026-05-12
"""orphan_candidates: filter to plugins with zero deps and zero records."""

from nexus.plugins.models import PluginInfo, PluginInventory

__all__ = ["orphan_candidates"]


def orphan_candidates(inventory: PluginInventory) -> tuple[PluginInfo, ...]:
    """Return plugins with no dependents and no scope-owned records.

    Plugins with ``record_count is None`` (not captured yet) are
    excluded -- the criterion requires evidence of zero records,
    not absence of data.

    Args:
        inventory: Captured plugin inventory.

    Returns:
        Tuple of orphan plugins sorted by ``(state asc, plugin_id asc)``.
        Active plugins sort before inactive plugins.
    """
    has_dependents: set[str] = set()
    for plugin in inventory.plugins:
        for dep in plugin.depends_on:
            has_dependents.add(dep)
    orphans = [
        p
        for p in inventory.plugins
        if p.plugin_id not in has_dependents and p.record_count == 0
    ]
    orphans.sort(key=lambda p: (p.state, p.plugin_id))
    return tuple(orphans)
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_orphans.py -v`

Expected: 8 PASS.

- [ ] **Step 5: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/orphans.py tests/test_plugins_orphans.py
.venv/Scripts/pyright src/nexus/plugins/orphans.py tests/test_plugins_orphans.py
```

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/orphans.py tests/test_plugins_orphans.py
git commit -m "feat(plugins): add orphan_candidates pure function

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Public re-export

**Files:**
- Modify: `src/nexus/plugins/__init__.py`
- Modify: `tests/test_plugins_orphans.py`

- [ ] **Step 1: Append failing test**

Add at the BOTTOM of `tests/test_plugins_orphans.py`:

```python
import nexus.plugins as plugins_pkg


def test_public_api_reexports_orphan_candidates() -> None:
    assert "orphan_candidates" in plugins_pkg.__all__
    assert hasattr(plugins_pkg, "orphan_candidates")
```

The `import nexus.plugins as plugins_pkg` goes at the TOP of the file with the other imports, NOT inside the function (ruff PLC0415).

- [ ] **Step 2: Run; expect FAIL**

`.venv/Scripts/python -m pytest tests/test_plugins_orphans.py::test_public_api_reexports_orphan_candidates -v`

- [ ] **Step 3: Update `src/nexus/plugins/__init__.py`**

Add the import and add `orphan_candidates` to `__all__` (alphabetical). Replace the file contents:

```python
# src/nexus/plugins/__init__.py
# Public re-exports for the plugins layer.
# Author: Pierre Grothe
# Date: 2026-05-11
"""nexus.plugins: read-only plugin inventory layer.

Exports the data models, scanner, error types, product-family lookup,
the cross-instance diff/promote helpers, the update-detection filter,
the advisory checkers (EOL, CVE, license), the impact analyzer
(reverse-dep graph + scope record counts), and the orphan filter.
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
from nexus.plugins.orphans import orphan_candidates
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
    "orphan_candidates",
    "plugins_with_updates",
    "product_family_for",
    "project_to_promote_plan",
    "reverse_dependencies",
]
```

- [ ] **Step 4: Run; expect PASS**

`.venv/Scripts/python -m pytest tests/test_plugins_orphans.py::test_public_api_reexports_orphan_candidates -v`

- [ ] **Step 5: Verify**

```
.venv/Scripts/ruff check src/nexus/plugins/__init__.py tests/test_plugins_orphans.py
.venv/Scripts/pyright src/nexus/plugins/__init__.py tests/test_plugins_orphans.py
```

- [ ] **Step 6: Commit**

```bash
git add src/nexus/plugins/__init__.py tests/test_plugins_orphans.py
git commit -m "feat(plugins): expose orphan_candidates

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: `nexus plugins orphans` CLI command

**Files:**
- Modify: `src/nexus/cli.py`
- Create: `tests/test_cli_plugins_orphans.py`

- [ ] **Step 1: Modify `src/nexus/cli.py`**

Add an import line near the other `nexus.plugins` imports:

```python
from nexus.plugins.orphans import orphan_candidates
```

Update `_PLUGINS_HELP` (around line 109-117) to add the new command:

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
    ("orphans", "Show plugins with no dependents and no scope records"),
]
```

Append at the END of the plugins commands section (after the existing `plugins_impact` command and its helpers):

```python
_ORPHAN_STATES = ("active", "inactive")


@plugins_app.command("orphans")
def plugins_orphans(
    instance: Annotated[
        str,
        typer.Option(
            "--instance",
            help="Instance profile (default: configured default)",
        ),
    ] = "",
    state: Annotated[
        str,
        typer.Option(
            "--state",
            help="Filter to one plugin state: active or inactive.",
        ),
    ] = "",
) -> None:
    """Show plugins with no dependents AND no scope-owned records."""
    meta, inventory = _load_inventory_or_exit(instance)
    if all(p.record_count is None for p in inventory.plugins):
        console.print(
            Notice.warn(
                "Inventory has no record counts -- run nexus instance refresh to populate."
            )
        )
        console.print(
            Hint(label="Refresh", command=f"nexus instance refresh {meta.profile}")
        )
        raise typer.Exit(1)
    if state and state not in _ORPHAN_STATES:
        console.print(Notice.error(f"Unknown --state: {state}"))
        raise typer.Exit(1)
    candidates = orphan_candidates(inventory)
    if state:
        candidates = tuple(p for p in candidates if p.state == state)
    if not candidates:
        console.print(Notice.info("No orphan candidates."))
        return
    rows: list[list[RenderableType]] = [
        [
            p.plugin_id,
            p.name,
            "active" if p.state == "active" else "inactive (license slot)",
            "no records",
        ]
        for p in candidates
    ]
    console.print(
        DataTable(
            title="Orphan candidates",
            columns=[
                DataColumn(header="Plugin ID", width=32),
                DataColumn(header="Name", width=24),
                DataColumn(header="State", width=24),
                DataColumn(header="Records", width=12),
            ],
            rows=rows,
        )
    )
    console.print(Notice.info(f"{len(candidates)} orphan candidate(s)."))
```

- [ ] **Step 2: Create `tests/test_cli_plugins_orphans.py`**

```python
# tests/test_cli_plugins_orphans.py
# Tests for the nexus plugins orphans command.
# Author: Pierre Grothe
# Date: 2026-05-12
"""Tests for nexus plugins orphans."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nexus.cache import clear_cache
from nexus.cli import app
from nexus.config.paths import NexusPaths
from nexus.instances.models import InstanceMeta
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
    record_count: int | None = 0,
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
            "record_count": record_count,
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
        (profile_dir / "plugins.json").write_text(
            inv.model_dump_json(indent=2), encoding="utf-8"
        )


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    monkeypatch.setenv("NEXUS_CONFIG_PATH", str(tmp_path / "config.yaml"))
    clear_cache(NexusPaths.from_env)
    return CliRunner()


def test_orphans_renders_datatable_with_orphan_candidates(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.lonely", record_count=0),
            _info("com.busy", record_count=100),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans"])
    assert result.exit_code == 0
    assert "com.lonely" in result.output
    assert "com.busy" not in result.output
    assert "1 orphan candidate" in result.output


def test_orphans_prints_no_candidates_message_when_clean(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.busy", record_count=100),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans"])
    assert result.exit_code == 0
    assert "No orphan candidates" in result.output


def test_orphans_filters_by_state_active_when_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.alive", state="active", record_count=0),
            _info("com.dead", state="inactive", record_count=0),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans", "--state", "active"])
    assert result.exit_code == 0
    assert "com.alive" in result.output
    assert "com.dead" not in result.output


def test_orphans_filters_by_state_inactive_when_flag_provided(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (
            _info("com.alive", state="active", record_count=0),
            _info("com.dead", state="inactive", record_count=0),
        ),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans", "--state", "inactive"])
    assert result.exit_code == 0
    assert "com.dead" in result.output
    assert "com.alive" not in result.output


def test_orphans_errors_on_unknown_state_value(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", (_info("com.x", record_count=0),))
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans", "--state", "weird"])
    assert result.exit_code == 1
    assert "Unknown --state" in result.output


def test_orphans_warns_when_snapshot_has_no_record_counts(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(
        tmp_path,
        "prod",
        (_info("com.unrefreshed", record_count=None),),
    )
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans"])
    assert result.exit_code == 1
    assert "no record counts" in result.output.lower()
    assert "nexus instance refresh" in result.output


def test_orphans_warns_when_inventory_missing(
    runner: CliRunner, tmp_path: Path
) -> None:
    _seed(tmp_path, "prod", None)
    runner.invoke(app, ["instance", "use", "prod"])
    result = runner.invoke(app, ["plugins", "orphans"])
    assert result.exit_code == 1
    assert "nexus instance refresh" in result.output
```

- [ ] **Step 3: Run; expect FAIL on missing command**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_orphans.py -v`

- [ ] **Step 4: Run after CLI added; expect PASS**

`.venv/Scripts/python -m pytest tests/test_cli_plugins_orphans.py -v`

Expected: 7 PASS.

- [ ] **Step 5: Smoke check help**

`.venv/Scripts/nexus plugins orphans --help`

Expected: help text shows `--instance` and `--state` options.

- [ ] **Step 6: Verify**

```
.venv/Scripts/ruff check src/nexus/cli.py tests/test_cli_plugins_orphans.py
.venv/Scripts/pyright src/nexus/cli.py tests/test_cli_plugins_orphans.py
```

- [ ] **Step 7: Commit**

```bash
git add src/nexus/cli.py tests/test_cli_plugins_orphans.py
git commit -m "feat(cli): add nexus plugins orphans command

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Black + ratchet refresh + PR

**Files:**
- Modify: `.ratchet.json`

- [ ] **Step 1: Black**

`.venv/Scripts/black src/nexus/plugins/ src/nexus/cli.py tests/test_plugins_orphans.py tests/test_cli_plugins_orphans.py tests/test_plugins_scanner.py tests/test_plugins_models.py`

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
- `src/nexus/plugins/__init__.py`
- `src/nexus/plugins/models.py`
- `src/nexus/plugins/orphans.py`
- `src/nexus/plugins/scanner.py`

If `coverage.json` is tracked in the repo, restore it after measurement: `git checkout coverage.json`.

- [ ] **Step 4: Update `.ratchet.json`**

Update or insert the following keys with the freshly measured values. Do not change unrelated keys.

```jsonc
{
  ...
  "modules": {
    ...
    "nexus.cli": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.__init__": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.models": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.orphans": {"covered_lines": <new>, "total_lines": <new>},
    "nexus.plugins.scanner": {"covered_lines": <new>, "total_lines": <new>},
    ...
  }
}
```

Ratchet rule: `covered_lines` must be >= the previous value for each module; `total_lines` reflects the new module size.

- [ ] **Step 5: Commit**

```bash
git add .ratchet.json src/nexus/plugins/ src/nexus/cli.py tests/
git commit -m "chore(plugins): black formatting + refresh ratchet for orphans layer

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 6: Push + open PR**

```bash
git push -u origin feat/plugins-orphans
gh pr create --base feat/plugins-impact --title "feat(plugins): D3 orphan detection (zero deps + zero records)" --body "$(cat <<'EOF'
## Summary
- `nexus plugins orphans` lists plugins with no dependents AND no scope-owned records.
- `PluginInfo` gets a `record_count: int | None` field, populated at refresh time via a bounded-concurrency (cap=16) aggregate-API fan-out over `sys_metadata` grouped by `sys_class_name`.
- Refresh becomes ~5-15s slower; orphan/impact/future drift renders are instant.
- Partial fetch failures leave per-plugin `record_count` at `None` without aborting the refresh.

Sub-project D3 of plugin management. Stacked on PR #15 (`feat/plugins-impact`).

Spec: docs/superpowers/specs/2026-05-12-plugin-orphans-design.md
Plan: docs/superpowers/plans/2026-05-12-plugin-orphans.md

## Test plan
- [x] 8 new tests in `tests/test_plugins_orphans.py`
- [x] 7 new CLI tests in `tests/test_cli_plugins_orphans.py`
- [x] 10 new scanner tests in `tests/test_plugins_scanner.py` (sum + fetch_counts + scan integration)
- [x] 3 new model tests in `tests/test_plugins_models.py`
- [x] Full suite green except 4 pre-existing failures
- [x] ruff / black / mypy / pyright clean
- [x] `nexus plugins orphans --help` renders cleanly

EOF
)"
```

---

## Self-Review Summary

**Spec coverage:**
- record_count field on PluginInfo with default None -> Task 1
- _ScopeRecordCountError + _sum_scope_records private helpers -> Task 2
- _fetch_counts with bounded concurrency cap=16 -> Task 3
- Scanner integrates fan-out with model_copy reconstruction -> Task 4
- orphan_candidates pure function with all five edge-case rules (0 deps + 0 records, exclude record_count None, include inactive, exclude self-loop, sort state then plugin_id) -> Task 5
- Public re-export -> Task 6
- CLI command with empty-counts warning, unknown-state error, --state filter, no-orphans info -> Task 7
- Black + quality gate + ratchet refresh + PR -> Task 8

All spec sections trace to a task. No gaps.

**Placeholder scan:** No "TBD" / "TODO" / "etc." in the plan body. The `<new>` markers in Task 8's ratchet block are intentionally pinned to "measure then fill in" -- explicit instruction. The Task 4 note about pre-existing test breakage is a known-state-of-art adjustment that any TDD plan would have to address.

**Type consistency:** All signatures consistent:
- `_sum_scope_records(client, plugin_id) -> int` (Task 2) matches usage in Task 3.
- `_fetch_counts(client, plugin_ids, *, max_concurrency=16) -> dict[str, int | None]` (Task 3) matches usage in Task 4's `scan()`.
- `orphan_candidates(inventory) -> tuple[PluginInfo, ...]` (Task 5) matches usage in Task 7's CLI command.
- `_ScopeRecordCountError` naming consistent throughout (Tasks 2, 3, 4).
- `record_count` field name consistent in models (Task 1), scanner integration (Task 4), orphan function (Task 5), and CLI (Task 7).
