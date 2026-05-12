# Plugin Impact Analysis Design

Date: 2026-05-12
Status: approved, ready for implementation plan
Sub-project D2 of the plugin management roadmap.

## Goal

Show the user the deactivation blast radius of a plugin before they
toggle it off in ServiceNow. Two signals:

1. **Reverse dependency closure** -- which plugins (direct + transitive)
   list the target in their `sys_store_app.depends_on`. Derived in
   memory from the existing inventory snapshot; no extra REST calls.
2. **Scope-owned record counts** -- per-table counts of records owned
   by the target's scope. One live REST call to the Aggregate API.

Exposed through `nexus plugins impact <plugin_id>`.

## Non-goals

- **Cross-scope reference scan.** Finding foreign keys from other
  scopes pointing at the target's records is the textbook "what
  breaks" but requires reference-field discovery + per-table scans.
  Out of scope; tracked for D3 or a future sub-project.
- **Per-feature live customer-data impact.** No "this plugin has 30k
  incidents using it" lookups. The scope-owned record counts cover
  customizations (scripts, business rules, UI actions), not user
  data.
- **Cached counts in the inventory snapshot.** Counts are fetched
  live at `nexus plugins impact` time. Capturing them during
  `nexus instance refresh` would meaningfully slow the refresh path
  and stale data is the wrong default for an impact check.
- **Triggering deactivation.** No write path; this is informational.

## Architecture

### Layer placement

Inside the existing `nexus.plugins` layer alongside the advisories
module.

```
src/nexus/plugins/impact.py             -- NEW: graph walk + REST fetcher + compute_impact()
src/nexus/plugins/models.py             -- MODIFY: add ReverseDependency, ScopeRecordCount, PluginImpact
src/nexus/plugins/errors.py             -- MODIFY: add PluginImpactError
src/nexus/plugins/__init__.py           -- MODIFY: re-export new symbols
src/nexus/cli.py                        -- MODIFY: add `impact` subcommand;
                                           update _PLUGINS_HELP
```

### Two-phase design

Phase 1 -- pure graph walk over the in-memory inventory. Synchronous,
deterministic, fully unit-testable without httpx.

Phase 2 -- async REST call to the Aggregate API. Independently
testable via `httpx.MockTransport`.

Both pieces are joined by an `async def compute_impact(...)` orchestrator.

### Pydantic models (added to `models.py`)

```python
class ReverseDependency(BaseModel):
    """One plugin that transitively depends on the impact target.

    Attributes:
        plugin_id: SN plugin identifier.
        name: Display name from the inventory.
        state: ``active`` or ``inactive``.
        depth: 1 = direct dependent, 2 = depends on a direct, etc.
        via: Chain of plugin_ids from this plugin back to the target,
            inclusive of both endpoints.
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
        reverse_deps: All plugins that depend on the target, sorted
            by ``(depth asc, plugin_id asc)``.
        record_counts: Per-table record counts owned by the target's
            scope, sorted by ``count desc, table asc``. Empty tuple
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

`Annotated[int, Field(ge=0)]` rejects negative counts at model
construction. `_FROZEN` is the existing
`ConfigDict(frozen=True, strict=True, extra="forbid")` alias.

### `PluginImpactError` (added to `errors.py`)

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

### `src/nexus/plugins/impact.py`

```python
def reverse_dependencies(
    inventory: PluginInventory,
    target: str,
) -> tuple[ReverseDependency, ...]:
    """Walk the reverse dependency graph from ``target``.

    Args:
        inventory: Captured plugin inventory.
        target: The plugin_id whose dependents we want.

    Returns:
        Tuple of dependents sorted by (depth asc, plugin_id asc).
        Empty when no plugin lists ``target`` in its depends_on.

    Raises:
        PluginImpactError: If ``target`` is not present in ``inventory``.
    """


async def fetch_scope_record_counts(
    url: str,
    token: str,
    plugin_id: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[ScopeRecordCount, ...]:
    """Live aggregate query over sys_metadata.

    Args:
        url: Instance base URL.
        token: OAuth bearer token.
        plugin_id: Plugin scope to count records for.
        transport: Optional httpx transport for tests.

    Returns:
        Per-table counts sorted by (count desc, table asc).

    Raises:
        ScopeRecordCountError: On non-200 status, network error, or
            malformed response. compute_impact() catches this and
            collapses it into ``counts_available=False``.
    """


async def compute_impact(
    inventory: PluginInventory,
    target: str,
    *,
    url: str,
    token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PluginImpact:
    """Join the graph walk and the live aggregate call.

    Raises:
        PluginImpactError: If ``target`` is not in the inventory.
    """
```

`ScopeRecordCountError` is a private exception inside `impact.py`
that `compute_impact` catches to set `counts_available=False`.
It is NOT exposed in `nexus.plugins.errors` -- it is an
implementation detail of the fetcher, not a user-facing error type.

### Aggregate API query

```
GET /api/now/stats/sys_metadata
  ?sysparm_query=sys_scope.scope=<plugin_id>
  &sysparm_count=true
  &sysparm_group_by=sys_class_name
```

Response shape (per ServiceNow documentation):

```json
{
  "result": [
    {
      "stats": {"count": "8012"},
      "groupby_fields": [
        {"field": "sys_class_name", "value": "sys_script"}
      ]
    },
    ...
  ]
}
```

`count` is returned as a string -- we parse to int. A 200 with empty
`result` is valid (plugin owns nothing in sys_metadata).

### Graph walk algorithm

1. Build a reverse adjacency map once: `dep_id -> set of plugin_ids
   that depend on dep_id`. O(P + D) where D = total dependency edges.
2. BFS from `target`. Visited set keyed by `plugin_id` guards against
   cycles and re-visits.
3. For each visited plugin, record `(plugin_id, name, state, depth,
   via)`. Depth = BFS level (1 for direct dependents).
4. `via` chain is built by carrying the parent's chain + appending
   the current plugin_id. Final chain is `(dependent_id, ...,
   target_id)`.
5. Sort output by `(depth, plugin_id)`.

`target` is excluded from the output (it does not "depend on itself"
for impact purposes).

### CLI surface

```
nexus plugins impact <plugin_id> [--instance PROFILE]
```

No `--no-counts` flag in v1. The live aggregate call is fast
enough (single REST call, no pagination needed); failure is
gracefully degraded.

### CLI behaviour

1. `_acquire_token(instance)` -- existing helper at `src/nexus/cli.py:630`
   that returns `(registry, meta, token, expiry)`. It transparently
   refreshes / re-prompts on expired tokens, so the impact command
   inherits that UX for free.
2. `_load_inventory_or_exit(instance)` to obtain the cached
   `PluginInventory`.
3. `await compute_impact(inventory, plugin_id, url=meta.url, token=token)`.
4. Catch `PluginImpactError` -> `Notice.error("Plugin not found: <id>")`
   + `typer.Exit(1)`.
5. Render `DataTable("Reverse dependencies")` with columns Plugin ID,
   Name, State, Depth, Via. Sort already done by the function.
6. If `reverse_deps == ()`: skip the table; print
   `Notice.info(f"No plugins depend on {plugin_id}.")` instead.
7. If `counts_available`:
   - If `record_counts == ()`: print `Notice.info("No scope-owned
     records.")`.
   - Otherwise: render `DataTable("Scope-owned records")` with columns
     Table, Count. Sort already done.
8. If NOT `counts_available`: print
   `Notice.warn("Record counts unavailable -- could not reach instance.")`.
9. Trailing `Notice.info` with a one-line summary:
   `f"{len(reverse_deps)} dependent plugin(s); {total_records} records in scope {target}."`
   (or omit the records clause when counts unavailable).

`Via` column rendering: join the chain with `->`, e.g.
`com.exports->com.reports->com.dashboards->com.acme.helper`. Truncate
to column width via existing `_trunc` helper.

### Reuse from existing layers

- `PluginInventory` / `PluginInfo` -- consumed unchanged.
- `_acquire_token` (cli.py:630), `_load_inventory_or_exit` --
  existing helpers in `cli.py`.
- `DataTable`, `DataColumn`, `Notice` -- already exported from `nexus.ui`.
- `httpx.AsyncClient` + `httpx.MockTransport` -- already used by the
  scanner.

### Errors / edge cases

- **Unknown profile:** `InstanceNotFoundError` -> `Notice.error` + exit 1.
- **Missing inventory:** `Notice.warn` + Hint + exit 1.
- **Plugin not in inventory:** `PluginImpactError` -> `Notice.error` +
  exit 1.
- **No dependents:** Empty `reverse_deps`. CLI renders a friendly
  message instead of an empty table.
- **No scope-owned records:** Empty `record_counts` with
  `counts_available=True`. CLI renders friendly message.
- **REST 4xx/5xx:** `ScopeRecordCountError` raised in fetcher,
  caught in `compute_impact`. `counts_available=False`, exit 0.
- **REST network error:** Same as above.
- **Malformed response:** Same as above. Specifically: missing
  `result` key, `result` not a list, group entry missing
  `stats.count` or `groupby_fields`. All collapse into
  `counts_available=False`.
- **Cycle in graph (A -> B -> A):** Visited set short-circuits.
  Each plugin appears at most once at its shortest path depth.
- **Self-dependency (A -> A):** Target seeded into visited from the
  start; self-loop produces no finding.
- **Stale token:** Token refresh failure surfaces as a 401 from the
  Aggregate API -> `ScopeRecordCountError` -> `counts_available=False`.
  The reverse-deps section still renders correctly.

## Testing strategy

All tests use real fakes (no mocks). Test names match
`test_<function>_<scenario>`. New test files get the 4-line header.

### `tests/test_plugins_impact.py` (new)

Reverse-dep graph walk:
- `test_reverse_dependencies_returns_empty_when_no_dependents`
- `test_reverse_dependencies_finds_direct_dependents_at_depth_1`
- `test_reverse_dependencies_traverses_transitively`
- `test_reverse_dependencies_sets_via_chain_inclusive_of_endpoints`
- `test_reverse_dependencies_handles_cycles_without_infinite_loop`
- `test_reverse_dependencies_handles_self_dependency_without_loop`
- `test_reverse_dependencies_sorts_by_depth_then_plugin_id`
- `test_reverse_dependencies_raises_when_target_not_in_inventory`

Async record-count fetcher (uses `httpx.MockTransport`):
- `test_fetch_scope_record_counts_parses_aggregate_response`
- `test_fetch_scope_record_counts_returns_empty_tuple_when_result_empty`
- `test_fetch_scope_record_counts_sorts_by_count_desc_then_table_asc`
- `test_fetch_scope_record_counts_raises_on_non_200`
- `test_fetch_scope_record_counts_raises_on_malformed_response`

Orchestrator:
- `test_compute_impact_aggregates_reverse_deps_and_counts`
- `test_compute_impact_marks_counts_unavailable_when_fetch_fails`
- `test_compute_impact_propagates_plugin_not_found`

### `tests/test_plugins_models.py` (append)

- `test_reverse_dependency_accepts_all_required_fields`
- `test_scope_record_count_rejects_negative_count`
- `test_plugin_impact_is_frozen`

### `tests/test_cli_plugins_impact.py` (new)

- `test_impact_renders_reverse_deps_and_counts_tables`
- `test_impact_prints_no_dependents_message_when_none`
- `test_impact_warns_when_record_counts_unavailable`
- `test_impact_errors_when_plugin_not_in_inventory`
- `test_impact_warns_when_inventory_missing`

### Test fakes

Reuse `tests/fakes/fake_plugin_data.py` for inventory tests. Add a
small "dependency chain" PluginInventory factory inline in
`test_plugins_impact.py` (3-4 plugins arranged A -> B -> C is enough
to exercise transitivity).

For the async fetcher, the existing `httpx.MockTransport` pattern
from `tests/test_plugins_scanner.py` carries over verbatim.

For the CLI tests, reuse the established `_meta` / `_info` / `_seed`
/ `runner` pattern from `tests/test_cli_plugins_updates.py`
(per-file copies, as the other CLI tests do).

### Token injection for CLI tests

The CLI's record-count path calls a token-retrieval helper. CLI
tests inject a fake token via `monkeypatch.setattr` on that helper
rather than going through the keychain. Mirrors how
`test_cli_instance_refresh.py` already handles token mocking.

## File layout

New files:

```
src/nexus/plugins/impact.py
tests/test_plugins_impact.py
tests/test_cli_plugins_impact.py
```

Modified files:

```
src/nexus/plugins/models.py            -- add 3 new models
src/nexus/plugins/errors.py            -- add PluginImpactError
src/nexus/plugins/__init__.py          -- re-export new symbols
src/nexus/cli.py                       -- add `impact` subcommand;
                                          update _PLUGINS_HELP
tests/test_plugins_models.py           -- 3 new tests
.ratchet.json                          -- new module baselines + cli.py bump
```

## Risks

- **Aggregate API permissions.** Some SN roles cannot query
  `/api/now/stats/sys_metadata`. A 403 collapses into
  `counts_available=False` rather than failing the whole command,
  so the reverse-deps section still ships. Document the role
  requirement in the Notice text.
- **Aggregate API timeout on huge scopes.** Plugins with hundreds of
  thousands of customizations might exceed the 60s default httpx
  timeout. v1 accepts this as a degradation: timeout -> warning.
  Increasing the timeout is a small follow-up.
- **`sys_metadata` is not the whole story.** Some customizations
  live outside `sys_metadata` (e.g. dictionary entries via
  `sys_dictionary`). v1 covers the common case (scripts, business
  rules, UI actions, flows). A more comprehensive "owned records"
  picture would require scanning a curated list of "always relevant"
  tables in addition; deferred.
- **Plugin removal vs deactivation.** Deactivation typically
  preserves records and marks them inactive; removal deletes them.
  This command does not distinguish between the two scenarios -- it
  shows what EXISTS, leaving the destructive-vs-reversible
  interpretation to the user.

## Out of scope (deferred)

- Cross-scope reference scan (foreign keys from other scopes
  pointing at target records).
- Record counts captured at refresh-time.
- `--no-counts` flag for offline mode.
- Triggering deactivation.
- Per-feature customer-data impact (incidents, problems, etc.).
- JSON output (`--format json`).

## Open questions

None remain after brainstorming. Scope (reverse-deps + scope-owned
counts), depth (transitive closure), data source (live aggregate
API), error model (graceful degradation on REST failures), and CLI
shape (single positional arg + `--instance` only) were all resolved
before this spec was written.
