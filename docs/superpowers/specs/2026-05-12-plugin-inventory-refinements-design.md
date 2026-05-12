# Plugin Inventory Refinements -- Design Spec

**Sub-project:** I
**Status:** Approved for implementation
**Date:** 2026-05-12
**Author:** Pierre Grothe
**Branch:** `feat/plugins-inventory-refinements` (from `main` at SHA `5fae099`)

## Goal

Tighten the plugin-inventory capture pipeline with two coordinated changes:

1. **Persist the per-table record-count breakdown** that the scanner already
   computes but currently sums-and-discards. Enables a cache-first impact
   fast-path so `nexus plugins impact <id>` does not re-query SN every time.
2. **Replace fragile partial-page-break pagination** in
   `PluginScanner._fetch` with RFC 5988 Link-header walking, eliminating
   silent truncation when SN returns a full-but-last page.

Both ride on one model field shift -- `PluginInfo.record_count: int | None`
becomes `PluginInfo.record_counts: tuple[ScopeRecordCount, ...] | None`,
reusing the existing `ScopeRecordCount` model already used by `PluginImpact`.

## Non-Goals

- Drift/diff on record-count changes. Counts churn constantly on live
  instances; surfacing those deltas would be noise. Drift remains
  inventory-shape only (added / removed / version / state).
- Capture-layer `record_count` (`manifest.record_count`, `ref.record_count`).
  Different model, different concept -- untouched.
- Schema-versioned inventory migration. Pre-release tool; invalidate old
  on-disk files with a friendly hint and require a refresh.
- Public re-export of `total_records` from `nexus.plugins` package. Helper
  stays at module level; promote only if a non-plugins caller emerges.

## Architecture

One pure model change cascades through five consumer modules:

```
models.py     -- record_count: int | None  =>  record_counts: tuple[ScopeRecordCount, ...] | None
              -- new helper: total_records(info) -> int | None
                       |
                       +-> scanner.py     -- persists buckets directly (no sum)
                       +-> scanner.py     -- _fetch uses Link header (independent change)
                       +-> orphans.py     -- total_records(p) == 0 filter
                       +-> impact.py      -- cache-first fast-path + --live opt-in
                       +-> registry.py    -- ValidationError -> invalidate old files
                       +-> cli.py         -- --live flag on plugins impact
```

No new modules, no new commands. Public API unchanged except the `--live` flag.

## Components

### 1. Model field shift (`src/nexus/plugins/models.py`)

**Current:**

```python
class PluginInfo(BaseModel):
    ...
    record_count: int | None = None
```

**After:**

```python
class PluginInfo(BaseModel):
    ...
    record_counts: tuple[ScopeRecordCount, ...] | None = None


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

`__all__` gains `total_records`. Docstring on `record_counts` documents the
sorted-`(count desc, table asc)` invariant (already true at fetch time).

### 2. Scanner -- preserve breakdown (`src/nexus/plugins/scanner.py`)

**Current internal helper:**

```python
async def _sum_scope_records(client, plugin_id) -> int:
    buckets = await _fetch_scope_counts_with_client(client, plugin_id)
    return sum(b.count for b in buckets)
```

**After:** delete `_sum_scope_records` and `_ScopeRecordCountError` shim;
call `_fetch_scope_counts_with_client` directly inside `_fetch_counts`.

`_fetch_counts` signature changes:

```python
async def _fetch_counts(
    client: httpx.AsyncClient,
    plugin_ids: tuple[str, ...],
    *,
    max_concurrency: int = _DEFAULT_COUNTS_CONCURRENCY,
) -> dict[str, tuple[ScopeRecordCount, ...] | None]: ...
```

Per-plugin failure path is unchanged in shape: `None` entry in the dict on
any `ScopeRecordCountError` from the inner helper.

`scan()` then uses:

```python
by_id = {
    pid: info.model_copy(update={"record_counts": counts.get(pid)})
    for pid, info in by_id.items()
}
```

### 3. Scanner -- Link-header pagination (`src/nexus/plugins/scanner.py`)

**Current pagination shape:**

```python
offset = 0
for _ in range(_MAX_PAGES):
    resp = await client.get(
        f"/api/now/table/{table}",
        params={"sysparm_fields": fields,
                "sysparm_limit": _PAGE_LIMIT,
                "sysparm_offset": offset},
    )
    if resp.status_code != 200: return [], (table, resp.status_code)
    page = resp.json().get("result", [])
    if not page: break
    rows.extend(page)
    if len(page) < _PAGE_LIMIT: break
    offset += _PAGE_LIMIT
```

**After:** first call uses `params=...` so httpx handles encoding; subsequent
calls use the absolute URL returned in the Link header.

```python
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
        table, _MAX_PAGES, len(rows),
    )
return rows, None
```

**New helper:**

```python
_NEXT_LINK_RE = re.compile(r'<([^>]+)>\s*;\s*rel\s*=\s*"?next"?', re.IGNORECASE)

def _parse_next_link(header: str) -> str | None:
    """Return the URL marked rel=\"next\" in an RFC 5988 Link header, or None.

    Tolerant of whitespace and unquoted rel values. Returns the first match
    only; SN responses contain at most one rel=\"next\" entry.
    """
    if not header:
        return None
    match = _NEXT_LINK_RE.search(header)
    return match.group(1) if match else None
```

The initial URL is built with the path-and-query form rather than passing
params, so the loop body is uniform: every iteration just calls `client.get`
on whatever URL it has. SN's `Link` header returns an absolute URL; httpx
accepts absolute URLs even when the client has a `base_url` set.

### 4. Registry -- invalidate old files (`src/nexus/instances/registry.py`)

Wrap two existing methods:

```python
def load_plugin_inventory(self, profile: str) -> PluginInventory | None:
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

Symmetric change for `load_plugin_baseline` with a `"baseline ack"` phrasing
on the warning. The `ValidationError` import is already present in
`registry.py`.

### 5. Orphan detection (`src/nexus/plugins/orphans.py`)

```python
from nexus.plugins.models import PluginInfo, PluginInventory, total_records

orphans = [
    p for p in inventory.plugins
    if p.plugin_id not in has_dependents and total_records(p) == 0
]
```

Docstring updated: `record_counts is None` (was `record_count is None`).

### 6. Impact fast-path + --live (`src/nexus/plugins/impact.py`)

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

Cache returns directly when present; live call only when cache is absent
or `live=True`.

### 7. CLI -- --live flag (`src/nexus/cli.py`)

Add the `--live` flag to `plugins impact`:

```python
@plugins.command("impact")
@click.argument("plugin_id")
@click.option("--instance", help="Instance profile to query.")
@click.option("--format", "output_format", default="table", help="Output format (table | json).")
@click.option(
    "--live", is_flag=True, default=False,
    help="Force re-query of SN record counts, ignoring the cached breakdown.",
)
def plugins_impact(plugin_id: str, instance: str | None, output_format: str, live: bool) -> None:
    ...
    impact = asyncio.run(compute_impact(inventory, plugin_id, url=url, token=token, live=live))
```

Update line 1930 precheck:

```python
if all(p.record_counts is None for p in inventory.plugins):
    console.print(
        Notice.warn("Inventory has no record counts -- run nexus instance refresh to populate.")
    )
```

No other CLI changes. The `plugins impact` display block (lines 1872-1890)
already operates on `PluginImpact.record_counts: tuple[ScopeRecordCount, ...]`
and is shape-compatible.

## Data Flow

**Record counts (before vs. after):**

```
Today:
  SN /stats/sys_metadata
    -> buckets: tuple[ScopeRecordCount, ...]
    -> sum() -> int -> PluginInfo.record_count
                            |
                            +-> orphans:  == 0 filter
                            +-> impact:   == 0 fast-path; else LIVE CALL every time

After I:
  SN /stats/sys_metadata
    -> buckets: tuple[ScopeRecordCount, ...]
    -> PluginInfo.record_counts  (persisted as-is, sorted (count desc, table asc))
                            |
                            +-> total_records(info): sum helper for orphans
                            +-> impact:   serve from cache when not None
                                          live call only when None (or --live)
```

**Pagination (before vs. after):**

```
Today (scanner._fetch):
  offset = 0
  loop (MAX_PAGES):
    GET /api/now/table/<t>?...&sysparm_offset=<offset>&sysparm_limit=200
    if status != 200:               -> abort with (table, status)
    if page is empty:               -> break          # heuristic 1
    rows += page
    if len(page) < 200:             -> break          # heuristic 2 (FRAGILE)
    offset += 200

After I:
  url = /api/now/table/<t>?sysparm_fields=...&sysparm_limit=200
  loop (MAX_PAGES):
    GET <url>
    if status != 200:               -> abort with (table, status)
    rows += page                     (page may be empty -- harmless)
    url = _parse_next_link(resp.headers.get("Link", ""))
    if url is None:                 -> break          # authoritative
```

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| `plugins.json` or `plugins.baseline.json` has old `record_count` shape | `ValidationError` caught in registry load. Log `WARNING plugins.json schema outdated for profile=<x> -- run 'nexus instance refresh' to rebuild`. Return None. Caller treats profile as having no inventory/baseline (same path as a fresh profile). |
| `plugins.json` corrupted (not just schema mismatch) | Same path as above. One warning covers both -- `ValidationError` is broad. |
| Per-plugin scope-count call fails during scan | Already handled. Per-plugin `None` in the dict. With new shape that becomes `PluginInfo.record_counts=None`. Scan succeeds with partial data. |
| Link header absent on a response that may have more rows | Pagination terminates. This is the authoritative SN signal; if it is stripped that is a SN configuration problem, not a NEXUS problem. |
| Link header malformed | `_parse_next_link` returns `None` -> clean termination. |
| `_MAX_PAGES` cap hit | Same WARNING + truncation as today. |
| `compute_impact(..., live=True)` and SN unreachable | `counts_available=False`. No silent fallback to stale cache when user explicitly asked for live data. |
| `compute_impact(...)` (default) and cache absent and SN unreachable | `counts_available=False`. Same as today. |

## Testing

### Test files touched

| File | Changes |
|------|---------|
| `tests/test_plugins_models.py` | Add `test_total_records_with_none_returns_none`, `test_total_records_with_empty_tuple_returns_zero`, `test_total_records_with_single_bucket_returns_count`, `test_total_records_with_multi_bucket_returns_sum`. Update existing `PluginInfo` fixtures: drop `record_count`, use `record_counts`. |
| `tests/test_plugins_scanner.py` | Add `test_fetch_follows_link_header_next`, `test_fetch_stops_when_no_next_link`, `test_fetch_with_malformed_link_terminates_cleanly`, `test_fetch_with_empty_link_header_terminates`, `test_fetch_handles_link_header_with_other_rels`, `test_fetch_respects_max_pages_cap`. Update count tests: assert tuple-shape `record_counts` persistence (`test_scan_populates_record_counts_breakdown`). Remove tests asserting the old scalar shape. |
| `tests/test_plugins_orphans.py` | Update fixtures: zero-records cases use `record_counts=()`, unknown-records use `record_counts=None`. Test names stay (behaviour-named, not field-named). |
| `tests/test_plugins_impact.py` | Add `test_compute_impact_serves_from_cache_when_record_counts_populated` (no live call), `test_compute_impact_live_flag_forces_refetch_despite_cache`, `test_compute_impact_falls_back_to_live_when_record_counts_none`. Keep existing failure-mode tests; update their fixtures. |
| `tests/test_cli_plugins_impact.py` | Add `test_plugins_impact_live_flag_passes_through`, `test_plugins_impact_default_uses_cache`. |
| `tests/test_cli_plugins_orphans.py` | Update precheck-warning test for the new `record_counts is None` predicate. |
| `tests/test_instances_registry.py` | Add `test_load_plugin_inventory_with_legacy_shape_returns_none_and_warns`, `test_load_plugin_baseline_with_legacy_shape_returns_none_and_warns`. Fixtures write an old-shape JSON literal to disk via `Path.write_text`. |

### Approach

- **No mocks.** Scanner tests use `httpx.MockTransport` returning real
  `httpx.Response` objects with `Link` headers passed via
  `headers={"Link": ...}`.
- **Registry legacy-shape tests** write the literal old JSON via
  `Path.write_text`, then call the load method and assert
  `(result is None) and ("schema outdated" in caplog.text)`.
- **Impact cache tests** use a counting transport that records calls; assert
  `transport.call_count == 0` to verify the live call was skipped.
- `caplog.set_level(logging.WARNING)` to assert the schema-outdated and
  cache-stale warnings fire.

### Coverage targets

| Module | Lines impact |
|--------|-------------|
| `models.py` | +5-7 (helper + tests) |
| `scanner.py` | +5 (Link parser); -8 (offset arithmetic removed) |
| `orphans.py` | +/- 0 (one line swapped) |
| `impact.py` | +3 (live param + cache branch) |
| `registry.py` | +6 (two try/except blocks) |

`.ratchet.json` to be updated after the green run.

## Out of Scope

- Schema versioning for inventory files. If a second migration ever
  becomes necessary, introduce versioning then.
- Surfacing the per-table breakdown in `plugins inventory` CLI output. The
  inventory table view stays a one-line-per-plugin summary; the breakdown
  is shown in `plugins impact <id>` (already does so via `PluginImpact`).
- Migrating G/H test fixtures that touch `record_count`. They are updated
  inline as part of this sub-project's test pass.
- Promoting `total_records` to the public `nexus.plugins` re-export. Stays
  at `nexus.plugins.models`; promote when a non-plugins caller emerges.
