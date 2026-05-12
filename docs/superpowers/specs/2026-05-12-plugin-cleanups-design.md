# Plugin Cleanups Design

Date: 2026-05-12
Status: approved, ready for implementation plan
Sub-project G of the plugin management roadmap.

## Goal

Land six surgical cleanups noted while shipping sub-projects A through
D3. None of them is a new feature; each tightens what's already in
place. Shipped as one PR with six small commits so each item is
reviewable in isolation.

## Items

1. **Scanner pagination loop.** Fix the pre-existing 200-row
   truncation in `PluginScanner._fetch`.
2. **DRY: shared aggregate-API helper.** Extract the parsing logic
   shared by `scanner._sum_scope_records` and
   `impact.fetch_scope_record_counts` into one private helper.
3. **`nexus plugins impact` reuses cached record counts (zero
   case).** Skip the live REST call when the target plugin's cached
   `record_count == 0`.
4. **`nexus instance refresh --no-counts` opt-out flag.** Lets users
   skip the D3 aggregate-API fan-out when they don't need orphan
   detection.
5. *(Skipped -- drift detection is sub-project H.)*
6. **`--format text|json` across seven plugin commands.** Adds
   machine-readable output for CI/scripting integration.
7. **`--strict` flag on `nexus plugins advisories`.** Exits non-zero
   when findings exist (CI gating).

## Non-goals

- **Drift detection.** Sub-project H.
- **Per-table breakdown caching.** Current impact command still needs
  a live REST call when records exist, because `PluginInfo.
  record_count` is a total, not a per-class-name map. Caching the
  breakdown is a future enhancement.
- **Top-level `--format` option.** Per-command flags are the typer
  idiom here; a global flag would require restructuring every
  rendering helper.
- **YAML output.** `nexus plugins export` and `promote` already write
  YAML to files; the new `--format` flag covers JSON-to-stdout
  specifically.

## Architecture

All six items are local edits to existing files. No new files, no
new layers, no Pydantic model changes.

```
src/nexus/plugins/scanner.py        -- items 1, 2, 4
src/nexus/plugins/impact.py         -- items 2, 3
src/nexus/cli.py                    -- items 3, 4, 6, 7
```

### Item 1 -- Scanner pagination

Current `PluginScanner._fetch` issues one GET with `sysparm_limit=200`
and returns the result. Replace with a paginating loop:

```python
async def _fetch(
    self, client: httpx.AsyncClient, table: str, fields: str
) -> tuple[list[dict[str, object]], tuple[str, int] | None]:
    """Fetch a Table API endpoint, paginated until exhausted."""
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

`_PAGE_LIMIT = 200` stays as-is. New constant `_MAX_PAGES = 50`
(10,000 plugins). The early-exit when `len(page) < _PAGE_LIMIT` saves
one request when the last page is partial.

The `for ... else` form is intentional: the `else` runs only when the
loop completes without `break`, i.e. when the page cap is hit. A
WARNING log lets the user know data may be missing.

### Item 2 -- Shared aggregate-API helper

Today's duplication:
- `impact.fetch_scope_record_counts(url, token, plugin_id, *, transport)`
  opens its own httpx client, makes a stats call, parses the response
  into `tuple[ScopeRecordCount, ...]`.
- `scanner._sum_scope_records(client, plugin_id)` makes the same call
  with an existing client, but parses for a different shape
  (single int sum).

Extract `_fetch_scope_counts_with_client(client, plugin_id) -> tuple
[ScopeRecordCount, ...]` as a private module-level function in
`impact.py`:

```python
async def _fetch_scope_counts_with_client(
    client: httpx.AsyncClient,
    plugin_id: str,
) -> tuple[ScopeRecordCount, ...]:
    """Aggregate query over sys_metadata using an existing client.

    Shared inner helper. ``fetch_scope_record_counts`` wraps this with
    its own client. The scanner's ``_sum_scope_records`` calls this
    directly with its scan-time client and sums the result.

    Raises:
        ScopeRecordCountError: On non-200 status, network error, or
            malformed response.
    """
    # body identical to the current parsing in fetch_scope_record_counts
```

Refactor `fetch_scope_record_counts` to be a thin wrapper:

```python
async def fetch_scope_record_counts(
    url: str,
    token: str,
    plugin_id: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[ScopeRecordCount, ...]:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient(
            base_url=url, headers=headers, timeout=30.0, transport=transport
        ) as client:
            return await _fetch_scope_counts_with_client(client, plugin_id)
    except httpx.RequestError as exc:
        raise ScopeRecordCountError(f"network error: {exc}") from exc
```

Refactor `scanner._sum_scope_records` to delegate:

```python
async def _sum_scope_records(
    client: httpx.AsyncClient, plugin_id: str
) -> int:
    """Return total records in ``plugin_id``'s scope (sum of per-table counts)."""
    from nexus.plugins.impact import (  # local to avoid module-load cycle
        _fetch_scope_counts_with_client,
        ScopeRecordCountError,
    )
    try:
        buckets = await _fetch_scope_counts_with_client(client, plugin_id)
    except ScopeRecordCountError as exc:
        raise _ScopeRecordCountError(str(exc)) from exc
    return sum(b.count for b in buckets)
```

**Note on the cross-module import.** Scanner.py currently does not
import from impact.py (siblings in the same layer). The new local
import keeps the module-load order stable -- impact.py imports
PluginInventory from models, so a top-level import in scanner.py
could create a cycle once future code adds impact-side imports of
scanner. Local import is the safer choice.

Alternative: move `_fetch_scope_counts_with_client` to a new
`src/nexus/plugins/_aggregate_api.py` private module. Slightly
cleaner but adds a file. Local-import-in-helper is enough for v1.

### Item 3 -- Impact uses cached counts (zero case)

In `compute_impact`, before the live REST call, look up the target's
cached `record_count`:

```python
async def compute_impact(
    inventory: PluginInventory,
    target: str,
    *,
    url: str,
    token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PluginImpact:
    """..."""
    deps = reverse_dependencies(inventory, target)
    target_info = next(p for p in inventory.plugins if p.plugin_id == target)

    # Fast-path: cached zero -> no live call needed.
    if target_info.record_count == 0:
        return PluginImpact(
            target_plugin_id=target,
            target_name=target_info.name,
            reverse_deps=deps,
            record_counts=(),
            counts_available=True,
        )

    # Otherwise live call (cached > 0 needs per-table breakdown;
    # cached None means no data).
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

The existing CLI render path already handles `counts_available=True`
+ `record_counts=()` correctly -- it prints "No scope-owned records."
No CLI change needed.

### Item 4 -- `--no-counts` flag on refresh

`PluginScanner.scan` gets a new keyword-only parameter:

```python
async def scan(
    self,
    url: str,
    token: str,
    sn_version: str,
    *,
    capture_counts: bool = True,
) -> PluginInventory:
    """..."""
    async with httpx.AsyncClient(...) as client:
        ...
        if capture_counts:
            counts = await _fetch_counts(client, tuple(by_id.keys()))
            by_id = {
                pid: info.model_copy(update={"record_count": counts.get(pid)})
                for pid, info in by_id.items()
            }
    # else: record_count stays None on every plugin
    return PluginInventory(...)
```

CLI side (`nexus instance refresh`):

```python
@instance_app.command("refresh")
def instance_refresh(
    profile: str = typer.Argument(""),
    no_counts: Annotated[
        bool,
        typer.Option(
            "--no-counts",
            help="Skip per-plugin record count capture (faster refresh).",
        ),
    ] = False,
) -> None:
    """..."""
    ...
    scanner = PluginScanner()
    inventory = asyncio.run(
        scanner.scan(
            meta.url, token, meta.sn_version, capture_counts=not no_counts
        )
    )
    ...
```

### Item 6 -- `--format text|json` on seven commands

Helper near the top of `cli.py`:

```python
_FORMATS = ("text", "json")


def _validate_format(value: str) -> None:
    """Raise typer.Exit(1) with Notice.error on unknown format value."""
    if value not in _FORMATS:
        console.print(Notice.error(f"Unknown --format: {value}"))
        raise typer.Exit(1)


def _emit_json(model: BaseModel) -> None:
    """Print model JSON serialization to stdout, one line."""
    print(model.model_dump_json())
```

Each affected command gets a `--format` option:

```python
@plugins_app.command("advisories")
def plugins_advisories(
    ...,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
) -> None:
    _validate_format(output_format)
    ...
    # existing filter/load logic
    if output_format == "json":
        _emit_json(AdvisorySet(findings=findings))
        return
    # existing Rich rendering
    ...
```

Affected commands:
- `nexus plugins list` -> emits the filtered `PluginInventory` (or a
  light wrapper with just the matching plugins).
- `nexus plugins info <plugin_id>` -> emits the single `PluginInfo`.
- `nexus plugins diff <a> <b>` -> emits the `PluginDiff` model.
- `nexus plugins advisories` -> emits the filtered `AdvisorySet`.
- `nexus plugins impact <plugin_id>` -> emits the `PluginImpact` model.
- `nexus plugins orphans` -> emits a thin `OrphanReport` wrapper
  (since the return type is `tuple[PluginInfo, ...]`, we need to wrap
  it for a stable JSON top-level shape).
- `nexus plugins updates` -> emits a thin `UpdatesReport` wrapper.

**Wrapper models for orphans / updates:** define inline in `cli.py`
as frozen BaseModels. Single field `plugins: tuple[PluginInfo, ...]`
or `updates: tuple[PluginInfo, ...]`. Keeps the public `nexus.plugins`
API unchanged; the wrappers are CLI-internal.

### Item 7 -- `--strict` flag on advisories

```python
@plugins_app.command("advisories")
def plugins_advisories(
    ...,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit with code 1 if any findings remain after filters.",
        ),
    ] = False,
) -> None:
    ...
    # Apply --type and --severity filters first, then check --strict.
    if not findings:
        # text mode: print "No advisories found."; exit 0 regardless of --strict
        ...
        return
    # Render (text or json)
    ...
    if strict:
        raise typer.Exit(1)
```

Exit code 1 for "findings present" matches the modern Python tooling
convention (ruff, mypy, black --check, flake8): 0 = clean, 1 =
findings / policy violations / tool failure, 2 = misuse / Typer
UsageError.

Without `--strict`, exit is always 0 even when findings exist
(informational mode). The error paths (corrupted advisory data,
missing inventory) already exit 1 -- this is an acceptable conflation
because a CI step using `--strict` only checks "did the command
succeed cleanly" which is true for both "no findings" and "tool
worked correctly". If the user needs strict separation, they can
parse the JSON output (item 6) for an explicit `findings == []`
check.

The `--strict` flag interacts with `--format json` cleanly: JSON is
still emitted on stdout, then the non-zero exit fires.

## Reuse from existing layers

- `Notice` / `Hint` / `DataTable` / `DataColumn` -- already exported.
- `console.print_json` is available via Rich; for JSON we use plain
  `print(model.model_dump_json())` to avoid Rich's pretty-printing
  (CI wants raw JSON).
- `PluginScanner`, `compute_impact`, `compute_advisories`,
  `orphan_candidates`, `plugins_with_updates`, `compute_diff` --
  unchanged signatures.

## Errors / edge cases

- **Unknown `--format` value:** caught by `_validate_format` -> exit 1.
- **`--strict` with no findings:** exit 0 (no findings means nothing
  is wrong).
- **`--strict` with `--severity` filter that excludes everything:**
  exit 0 -- the filter is part of the user's intent.
- **`--no-counts` on `nexus instance refresh`:** silently skips fan-out.
  Subsequent `nexus plugins orphans` will see all `record_count=None`
  and print the existing "Inventory has no record counts" warning.
- **Pagination cap hit (`_MAX_PAGES`):** WARNING log + partial data
  returned. Inventory is incomplete but still usable.
- **Item 3 cached zero on a plugin that has live records:** can happen
  if records were added AFTER the snapshot was captured. Behaviour:
  shows "No scope-owned records" until the next refresh. Acceptable
  staleness window. Documented.

## Testing strategy

All tests use real fakes (no mocks). Test names match
`test_<function>_<scenario>`. Approximately 22 new tests.

### `tests/test_plugins_scanner.py` (append)

Item 1:
- `test_fetch_paginates_through_multiple_pages` -- 200+200+50+0 = 450.
- `test_fetch_stops_at_max_pages_with_warning` -- never-empty handler,
  assert WARNING log and bail at cap.

Item 4:
- `test_scan_skips_count_fan_out_when_capture_counts_false` --
  `capture_counts=False`; assert no stats requests; assert all
  `record_count is None`.

### `tests/test_plugins_impact.py` (append)

Item 2:
- `test_fetch_scope_counts_with_client_returns_typed_buckets` --
  direct test of the new private helper.

Item 3:
- `test_compute_impact_skips_live_call_when_cached_record_count_is_zero`
- `test_compute_impact_calls_live_when_cached_record_count_is_positive`
- `test_compute_impact_calls_live_when_cached_record_count_is_none`

### `tests/test_cli_instance.py` (existing -- the refresh CLI tests live here)

Item 4:
- `test_instance_refresh_no_counts_flag_skips_count_capture`

### Per-command CLI test files (append)

Item 6 (one positive + one negative per command):
- `tests/test_cli_plugins_list.py` -- `test_list_emits_json_when_format_flag_provided`, `test_list_errors_on_unknown_format_value`
- `tests/test_cli_plugins_info.py` (or same file if combined) -- analogous pair
- `tests/test_cli_plugins_diff.py` -- analogous pair
- `tests/test_cli_plugins_advisories.py` -- analogous pair
- `tests/test_cli_plugins_impact.py` -- analogous pair
- `tests/test_cli_plugins_orphans.py` -- analogous pair
- `tests/test_cli_plugins_updates.py` -- analogous pair

Item 7:
- `tests/test_cli_plugins_advisories.py` (append):
  - `test_advisories_strict_exits_1_when_findings_present`
  - `test_advisories_strict_exits_0_when_no_findings`
  - `test_advisories_strict_respects_severity_filter`

## File layout

Modified files:

```
src/nexus/plugins/scanner.py             -- pagination loop, capture_counts flag,
                                            delegate _sum_scope_records to impact
src/nexus/plugins/impact.py              -- extract _fetch_scope_counts_with_client,
                                            cached-zero fast-path in compute_impact
src/nexus/cli.py                         -- --no-counts on refresh,
                                            --format on 7 commands,
                                            --strict on advisories,
                                            _validate_format / _emit_json helpers
tests/test_plugins_scanner.py            -- 3 new tests
tests/test_plugins_impact.py             -- 4 new tests
tests/test_cli_instance.py               -- 1 new test (refresh tests live here)
tests/test_cli_plugins_*.py              -- 14 new tests (2 per command * 7 commands)
.ratchet.json                            -- new baselines for cli.py, scanner.py, impact.py
```

## Risks

- **Item 1 pagination cap.** `_MAX_PAGES = 50` × 200 rows/page = 10,000
  plugins. Real instances typically have <500 plugins, so the cap is
  comfortable. Larger instances would still see partial data with a
  warning, not a crash.

- **Page size of 200 is conservative.** ServiceNow's own performance
  guidance (KB2296506) recommends 2,000-3,000 rows per Table API
  page for bulk extracts. We keep 200 in v1 to stay well under any
  instance-level cap and to match the existing
  `_PAGE_LIMIT` constant; bumping to 1,000 is a future optimization
  if refresh latency becomes a concern.

- **`Link` header pagination is more robust than empty-result
  probing.** The Table API returns RFC 5988 `Link` headers with
  `rel="next"` indicating the next-page URL. v1 uses the simpler
  empty-result + short-page check (matches pysnow-style clients).
  Switching to Link-header parsing is a future improvement.

- **Deep-offset performance degradation.** SN's `sysparm_offset` has
  classic OFFSET-N latency growth on large tables. For `v_plugin` /
  `sys_store_app` (small tables, <500 rows typical) this never
  bites. For large `sys_metadata` queries (not in scope for this
  cleanup) one would prefer keyset-style pagination with a sorted
  unique field.
- **Item 2 cross-module import.** Scanner.py importing from impact.py
  (locally inside a function) is unusual in this codebase. The
  alternative is a third module
  (`src/nexus/plugins/_aggregate_api.py`). Local import is chosen for
  v1 because it avoids a file move and the cycle risk is minimal --
  if impact.py ever needs to import scanner, we'd revisit.
- **Item 3 staleness.** Plugin records added between refresh and the
  next `nexus plugins impact` call would be missed by the
  cached-zero fast-path. Mitigation: documented; `nexus instance
  refresh` is the user's lever.
- **Item 6 wrapper models for orphans/updates.** Defining inline
  Pydantic models in cli.py creates a small precedent. Acceptable
  because they're not part of the public `nexus.plugins` API.
- **Item 7 exit code 1 conflation.** `--strict` exits 1 on findings;
  the existing error paths (corrupted advisory data, missing
  inventory) also exit 1. A CI script that needs to distinguish
  "policy violation" from "tool failure" must parse the JSON output
  (item 6) for an explicit `findings == []` check. This matches the
  ruff / mypy / black convention and is more useful than the
  reversed grep convention (0 = match, 1 = no match) for a
  CI-gating tool.

## Out of scope (deferred)

- Drift detection (sub-project H).
- Per-table count caching in the inventory snapshot.
- Global `--format` option.
- YAML stdout output.
- `--format csv` (use `nexus plugins export` for CSV).
- **Larger page size / Link-header pagination.** Both are
  performance optimizations on top of the basic loop introduced
  by item 1.

## Open questions

None. The two design decisions (cached-zero fast-path scope; JSON
shape = `.model_dump_json()`) were resolved during brainstorming.
