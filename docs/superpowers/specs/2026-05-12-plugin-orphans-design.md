# Plugin Orphan Detection Design

Date: 2026-05-12
Status: approved, ready for implementation plan
Sub-project D3 of the plugin management roadmap.

## Goal

Identify installed plugins with no dependents and no scope-owned
records -- the strongest signal that a plugin is unused and a
candidate for deactivation or removal. Exposed through
`nexus plugins orphans`.

## Non-goals

- **Configuration drift detection.** Drift requires either a curated
  per-plugin baseline (massive curation burden) or remembered
  historical snapshots (NEXUS does not yet store more than the
  current snapshot per profile). Drift will be revisited as either
  an extension of sub-project B's diff helpers (historical-self vs
  current-self) or in sub-project F (governance).
- **"Low records" heuristic.** A plugin with 47 records may be
  perfectly used; record-count thresholds yield false positives.
  The orphan rule is binary: 0 records.
- **Customer-data sweep.** No "this plugin has 30k incidents
  associated with it" lookups. Orphan detection only considers
  `sys_metadata`-tracked customizations (scripts, business rules,
  UI actions, flows).
- **Auto-removal.** No write path; this is informational.

## Architecture

### Layer placement

Inside the existing `nexus.plugins` layer. One new file plus a
PluginInfo field and a scanner extension.

```
src/nexus/plugins/orphans.py            -- NEW: orphan_candidates() pure function
src/nexus/plugins/models.py             -- MODIFY: add record_count to PluginInfo
src/nexus/plugins/scanner.py            -- MODIFY: fan out aggregate API per plugin
src/nexus/plugins/__init__.py           -- MODIFY: re-export orphan_candidates
src/nexus/cli.py                        -- MODIFY: add `orphans` subcommand;
                                           update _PLUGINS_HELP
```

### Model change

Add one field to `PluginInfo`:

```python
class PluginInfo(BaseModel):
    ...existing fields...
    vendor: str = ""
    record_count: int | None = None      # NEW
```

Default of `None` keeps existing JSON snapshots loadable without
re-capture. The orphan rule requires `record_count == 0`
(a literal integer 0). Snapshots written before D3 ships have
`record_count = None` for every plugin, so the orphan command
will refuse to run on them and prompt for a refresh.

We do NOT add a `Field(ge=0)` constraint to `record_count`: the
field union with `None` complicates the `Annotated` typing for
minimal benefit. The scanner only ever writes non-negative
integers. A test covers the constructor accepting 0.

### Scanner change

`PluginScanner.scan()` currently:
1. Reads `v_plugin` and `sys_store_app` concurrently.
2. Builds a deduped `by_id` map.
3. Returns a `PluginInventory`.

After step 2, fan out one aggregate-API call per plugin to populate
`record_count`. With bounded concurrency (asyncio.Semaphore, default
limit 16) and ~200 plugins, this adds ~5-15s to a refresh.

```python
async def _fetch_counts(
    self,
    client: httpx.AsyncClient,
    plugin_ids: tuple[str, ...],
    *,
    max_concurrency: int = 16,
) -> dict[str, int | None]:
    """Concurrent aggregate-API fan-out.

    Returns a mapping ``plugin_id -> total record count`` (None on
    per-plugin failure). The whole refresh is allowed to succeed
    with partial data.
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _one(pid: str) -> tuple[str, int | None]:
        async with semaphore:
            try:
                total = await self._sum_scope_records(client, pid)
            except _ScopeRecordCountError as exc:
                log.warning("scan: count fetch failed for %s -- %s", pid, exc)
                return pid, None
            return pid, total

    results = await asyncio.gather(*(_one(pid) for pid in plugin_ids))
    return dict(results)


async def _sum_scope_records(
    self,
    client: httpx.AsyncClient,
    plugin_id: str,
) -> int:
    """One aggregate call; sum the per-table buckets."""
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
        raise _ScopeRecordCountError(f"malformed: {exc}") from exc
    total = 0
    for row in rows:
        try:
            total += int(row["stats"]["count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise _ScopeRecordCountError(f"bad row: {exc}") from exc
    return total
```

`_ScopeRecordCountError` is a private exception inside `scanner.py`
(named to mirror `ScopeRecordCountError` in `impact.py`, with a
leading underscore for stricter privacy -- the scanner one is never
exposed beyond its module, whereas impact's is module-public for
test imports). Not exposed at the public `nexus.plugins` layer.

**Aggregate query parameters** are validated against the Aggregate
API doc (Zurich API Reference, July 2025):

- `sysparm_query` accepts encoded queries; dot-walk like
  `sys_scope.scope=<plugin_id>` is standard.
- `sysparm_count=true` returns counts.
- `sysparm_group_by=<field>` returns one result row per distinct
  value of the field.
- Response shape: `result` is an ARRAY for grouped queries (not the
  usual object); each entry has `stats.count` (a STRING that we
  parse to int) and `groupby_fields` (a list of `{field, value}`
  dicts).
- Default `sysparm_limit=10000` is more than enough; distinct
  `sys_class_name` values are typically <200. We do not pass an
  explicit limit; the default suffices.

After `_fetch_counts` returns, the scanner reconstructs each
`PluginInfo` with `record_count` set via `model_copy`:

```python
counts = await self._fetch_counts(client, tuple(by_id.keys()))
by_id = {
    pid: info.model_copy(update={"record_count": counts.get(pid)})
    for pid, info in by_id.items()
}
```

### orphans.py -- pure function

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

### CLI surface

```
nexus plugins orphans [--instance PROFILE] [--state active|inactive]
```

- `--instance` resolves the profile (same as prior commands).
- `--state` filters the result to plugins of the given state.
  Empty default = show both.

### CLI behaviour

1. `_load_inventory_or_exit(instance)` -> `(meta, inventory)`.
2. If EVERY plugin in the inventory has `record_count is None`:
   the snapshot pre-dates the D3 scanner enhancement. Render
   `Notice.warn("Inventory has no record counts -- run nexus
   instance refresh to populate.")` + `Hint(label="Refresh",
   command=f"nexus instance refresh {meta.profile}")` +
   `typer.Exit(1)`.
3. Otherwise: `orphan_candidates(inventory)`.
4. Apply `--state` filter if provided. Unknown value ->
   `Notice.error(f"Unknown --state: {value}")` + exit 1.
5. If filtered result is empty: `Notice.info("No orphan
   candidates.")` + return (exit 0).
6. Render `DataTable("Orphan candidates")` with columns Plugin ID,
   Name, State (renders "active" or "inactive (license slot)"),
   Records (always "no records" in this view).
7. Trailing `Notice.info(f"{len(filtered)} orphan candidate(s).")`.

### Reuse from existing layers

- `PluginInventory` / `PluginInfo` -- consumed unchanged structurally
  except for the new `record_count` field with a backward-compatible
  default.
- `_resolve_profile`, `_load_inventory_or_exit` -- existing helpers
  in `cli.py`.
- `DataTable`, `DataColumn`, `Notice`, `Hint` -- already exported
  from `nexus.ui`.
- `httpx.AsyncClient` + `httpx.MockTransport` -- already used by the
  scanner.

### Errors / edge cases

- **Unknown profile:** `InstanceNotFoundError` -> `Notice.error` +
  exit 1.
- **Missing inventory:** existing helper handles -> `Notice.warn` +
  Hint + exit 1.
- **Unrefreshed snapshot:** all `record_count is None` -> dedicated
  warning + Hint + exit 1.
- **Plugin with `record_count is None`** but others have ints: that
  plugin is excluded from the orphan result. Partial-fetch
  resilience baked into the scanner makes this case realistic.
- **Plugin appears in its own `depends_on`** (self-loop): it appears
  in `has_dependents`, so it gets excluded from orphans even if
  `record_count == 0`.
- **Unknown `--state` value:** `Notice.error` + exit 1.
- **Scanner stats call throttled / rate-limited:** the affected
  plugins get `record_count=None`. Refresh succeeds; subsequent
  orphan command may underreport for those plugins.

## Testing strategy

All tests use real fakes (no mocks). Test names match
`test_<function>_<scenario>`. New test files get the 4-line header.

### `tests/test_plugins_models.py` (append)

- `test_plugin_info_accepts_record_count_field`
- `test_plugin_info_defaults_record_count_to_none`
- `test_plugin_info_accepts_record_count_zero`

### `tests/test_plugins_scanner.py` (append)

- `test_scan_populates_record_count_from_aggregate_api`
- `test_scan_sets_record_count_none_when_aggregate_call_fails`
- `test_scan_caps_concurrent_aggregate_calls`

The scanner tests extend the existing `_transport_for` helper to
also route `/api/now/stats/sys_metadata` requests. The concurrency
cap test uses a fake handler that increments a counter on entry,
decrements on exit, and asserts the max observed concurrency is
`<= 16`.

### `tests/test_plugins_orphans.py` (new)

- `test_orphan_candidates_returns_plugin_with_zero_deps_and_zero_records`
- `test_orphan_candidates_excludes_plugin_with_dependents`
- `test_orphan_candidates_excludes_plugin_with_records`
- `test_orphan_candidates_excludes_plugin_with_record_count_none`
- `test_orphan_candidates_includes_inactive_plugins`
- `test_orphan_candidates_excludes_plugin_in_its_own_depends_on`
- `test_orphan_candidates_sorts_by_state_then_plugin_id`
- `test_orphan_candidates_returns_empty_tuple_when_no_candidates`

### `tests/test_cli_plugins_orphans.py` (new)

- `test_orphans_renders_datatable_with_orphan_candidates`
- `test_orphans_prints_no_candidates_message_when_clean`
- `test_orphans_filters_by_state_active_when_flag_provided`
- `test_orphans_filters_by_state_inactive_when_flag_provided`
- `test_orphans_errors_on_unknown_state_value`
- `test_orphans_warns_when_snapshot_has_no_record_counts`
- `test_orphans_warns_when_inventory_missing`

### Test fakes

A small inline `_plugin(plugin_id, *, depends_on=..., record_count=...,
state=...)` factory in each test file (matches the D2 test pattern;
avoids polluting `tests/fakes/fake_plugin_data.py` which is shared
across older tests).

For the CLI tests, reuse the per-file `_meta` / `_seed` / `runner`
fixture pattern from `tests/test_cli_plugins_updates.py` and
`tests/test_cli_plugins_impact.py`.

## File layout

New files:

```
src/nexus/plugins/orphans.py
tests/test_plugins_orphans.py
tests/test_cli_plugins_orphans.py
```

Modified files:

```
src/nexus/plugins/models.py            -- add record_count field on PluginInfo
src/nexus/plugins/scanner.py           -- add _fetch_counts, _sum_scope_records,
                                          _ScopeRecordCountError; chain in scan()
src/nexus/plugins/__init__.py          -- re-export orphan_candidates
src/nexus/cli.py                       -- add `orphans` subcommand;
                                          update _PLUGINS_HELP
tests/test_plugins_models.py           -- 3 new tests
tests/test_plugins_scanner.py          -- 3 new tests
.ratchet.json                          -- new module baseline + cli.py / scanner.py bumps
```

## Risks

- **Refresh takes meaningfully longer.** ~5-15s of additional REST
  fan-out per refresh. If a user complains, the simplest mitigation
  is a `--no-counts` flag on `nexus instance refresh` (deferred --
  not in v1). The concurrency cap of 16 keeps the network surface
  bounded.
- **Aggregate API permissions.** Some SN roles cannot query
  `/api/now/stats/sys_metadata`. Least-privilege access requires
  `snc_platform_rest_api_access` plus read on `sys_metadata`;
  `admin` is sufficient. The scanner gracefully degrades to
  `record_count = None` per plugin on 401/403; orphan detection
  simply won't yield results until the role is fixed.
- **False positives -- "shadow used" plugins.** A plugin might own
  zero records in `sys_metadata` but still serve a purpose (e.g.
  Glide property providers, license-only plugins, table-creator
  plugins where the records live in user tables rather than
  metadata). The orphan command is a TRIAGE tool, not a verdict.
  The output text reads "Orphan candidates" -- not "Orphans".
- **Sort by state asc puts "active" before "inactive".** Alphabetic
  order. Coincidental but desirable -- active orphans are more
  actionable. Encode the ordering as `state asc` rather than relying
  on the alphabetic accident.

- **Pre-existing pagination cap on scanner reads** (not introduced
  here). `PluginScanner._fetch` calls `v_plugin` and `sys_store_app`
  with `sysparm_limit=200` and no pagination loop, so instances
  with >200 plugins in either table are silently truncated. Every
  prior sub-project (A through D2) inherits this; D3 inherits it
  too. Fixing the truncation is out of scope for D3 -- it's a
  separate cleanup that, when done, will improve orphan detection
  fidelity for free.

## Out of scope (deferred)

- **Drift detection** (any flavor). Tracked for B-extension or F.
- **`--no-counts` opt-out on refresh.** Add when refresh slowness
  bites.
- **Customer-data sweep** (records in user tables, not
  `sys_metadata`).
- **Auto-deactivation / removal.** Read-only.
- **JSON output (`--format json`).** Render-only in v1.
- **Reusing cached counts for `nexus plugins impact`.** The impact
  command still fetches counts live. A future cleanup can switch
  it to read the cached value when available; out of scope for D3.

- **DRY with `impact.fetch_scope_record_counts`.** The scanner's
  `_sum_scope_records` duplicates the aggregate-API request shape
  already implemented in `nexus.plugins.impact.fetch_scope_record_counts`.
  A consolidation pass could have the scanner call into impact and
  sum the per-table buckets. Deferred to keep modules loosely
  coupled in v1; revisit if a third caller appears.

- **Fix the pre-existing 200-row scanner truncation.** Worth a
  dedicated cleanup that adds pagination loops to
  `PluginScanner._fetch` and updates the existing snapshot tests.

## Open questions

None remain after brainstorming. Scope (orphans only), criterion
(0 deps + 0 records, ignoring record_count=None), counts source
(refresh-time scanner fan-out), inactive-plugin handling (included
by default with state filter), and CLI shape (single subcommand +
`--state`) were all resolved before this spec was written.
