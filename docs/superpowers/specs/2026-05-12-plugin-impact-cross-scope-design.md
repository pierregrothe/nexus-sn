# Plugin Impact -- Cross-Scope FK Scan -- Design Spec

**Sub-project:** J
**Status:** Approved for implementation
**Date:** 2026-05-12
**Branch:** `feat/plugins-impact-cross-scope` (from `main` at `28c5786`)

## Goal

Extend `compute_impact` to surface tables in *other* scopes that hold
foreign-key references pointing **into** the target plugin's scope.
Currently impact only reports reverse dependencies (graph walk) and
records owned by the plugin's scope. After J, users also see "who else
holds pointers into this scope" with per-(table, field) record counts.

## Non-Goals

- Bi-directional analysis (already covered by reverse-deps for one
  direction, scope records for the other).
- Soft references (sys_documentation / glide_choice). Hard-typed
  reference fields only.
- Caching cross-scope results on disk. Live REST call on every impact
  invocation (with `--no-cross-scope` opt-out).
- Display rich reference attribute metadata. Just table + field + count.

## Architecture

Three live REST calls compose the cross-scope scan:

```
1. List target's tables    -- query sys_db_object where sys_scope.scope=<plugin_id>
2. Find inbound references -- for each target table, query sys_dictionary
                               where internal_type=reference AND reference=<table>
3. Count records           -- for each (source_table, field), count rows where
                               <field> IS NOT NULL
```

All three live in `impact.py`. The orchestrator `compute_impact` calls
the new function alongside the existing reverse-dep walk and scope
record-count fetch.

## Data Model

### `CrossScopeRef` (`src/nexus/plugins/models.py`)

```python
class CrossScopeRef(BaseModel):
    """One table-field pair that references into the target scope.

    Attributes:
        source_scope: plugin_id of the scope owning ``source_table``.
        source_table: SN table holding the reference field.
        field: Column name of the reference (sys_dictionary.element).
        target_table: Target table being pointed to.
        record_count: Number of records in ``source_table`` with a
            non-null value in ``field``.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    source_scope: str
    source_table: str
    field: str
    target_table: str
    record_count: Annotated[int, Field(ge=0)]
```

### `PluginImpact` (additive change)

Add field:

```python
    cross_scope_refs: tuple[CrossScopeRef, ...] = ()
    cross_scope_available: bool = True
```

`cross_scope_refs` default empty tuple to keep existing fixtures
compatible. `cross_scope_available=False` when the scan was opt-out
(via `--no-cross-scope`) or failed network.

## Core Functions (added to `src/nexus/plugins/impact.py`)

### `fetch_cross_scope_refs`

```python
async def fetch_cross_scope_refs(
    url: str,
    token: str,
    plugin_id: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[CrossScopeRef, ...]:
    """Find tables in other scopes that reference into ``plugin_id``'s scope.

    Three-phase walk:
        1. List sys_db_object rows where sys_scope.scope=plugin_id.
        2. For each target table, query sys_dictionary for inbound refs.
        3. For each (source_table, field), count non-null values.

    Returns:
        Tuple of CrossScopeRef sorted by ``(record_count desc,
        source_scope asc, source_table asc, field asc)``.

    Raises:
        ScopeRecordCountError: When any of the three phases fails.
    """
```

### `compute_impact` update

```python
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
```

New `cross_scope` kwarg. When True, call `fetch_cross_scope_refs` and
populate the new fields. When False, return `cross_scope_refs=()` and
`cross_scope_available=False`. On any
`ScopeRecordCountError` from the cross-scope call, log WARNING and
also return `cross_scope_available=False` with empty tuple.

The cross-scope branch is independent from the existing record-count
branch (both run when relevant). They could run in parallel via
`asyncio.gather`. Plan does this.

## REST Endpoints

### Phase 1: List tables in target scope

```
GET /api/now/table/sys_db_object?sysparm_query=sys_scope.scope=<plugin_id>
                                &sysparm_fields=name
                                &sysparm_limit=200
```

### Phase 2: Find inbound references

For each `target_table` from Phase 1:

```
GET /api/now/table/sys_dictionary?sysparm_query=internal_type=reference^reference=<target_table>
                                  &sysparm_fields=name,element,sys_scope.scope
                                  &sysparm_limit=200
```

`name` is the source table; `element` is the field; `sys_scope.scope`
is the source scope. The result rows give us the (source_table,
field, source_scope, target_table) tuples.

### Phase 3: Count non-null values per (source_table, field)

```
GET /api/now/stats/<source_table>?sysparm_query=<field>ISNOTEMPTY&sysparm_count=true
```

Returns `{"result": {"stats": {"count": "N"}}}`.

## Concurrency

- Phase 2: gather across target tables under a semaphore (cap 8).
- Phase 3: gather across (source_table, field) pairs under a semaphore
  (cap 16, matching the existing scanner cap).

## CLI

`nexus plugins impact <id>`:
- New flag: `--no-cross-scope` (defaults to False; cross-scope enabled).
- Output gains a third DataTable "Cross-scope references" rendered
  after the existing two tables. Columns: Source scope, Source table,
  Field, Target table, Records.
- Summary line gains `; N cross-scope refs` suffix when non-empty.

When `cross_scope_available=False`:
- If `--no-cross-scope` was set: silent (user opted out).
- If the scan failed: print `Notice.warn("Cross-scope refs unavailable -- ...")`.

## Errors

Reuse the existing `ScopeRecordCountError` for any non-200 / parse failure
in the three-phase scan. No new error type.

## Testing

- `tests/test_plugins_impact.py`: ~10 new tests for
  `fetch_cross_scope_refs` (no inbound refs, one match, multi-match,
  HTTP failure in each phase, sort order) and the `cross_scope` kwarg
  on `compute_impact`.
- `tests/test_cli_plugins_impact.py`: tests for `--no-cross-scope` flag
  and the new output table.

All tests use `httpx.MockTransport`; no real network.

## Out of Scope

- Detecting orphan FK values (rows referencing deleted targets).
  Different problem; could be sub-project later.
- Suggesting a remediation plan for high-record-count cross-scope refs.
  Belongs in sub-project E.
- Filtering / pagination across many cross-scope refs. If the count
  grows, add `--top N` later.
