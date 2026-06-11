# Schema Product Catalog
# Design Spec
# Author: Pierre Grothe
# Date: 2026-06-11

## Problem

`nexus schema erd` requires a hardcoded area key (`ham-itsm`, `bcm`, etc.) defined
in `areas.py`. Adding a new product combination requires editing Python source and
cutting a release. Solution Consultants do not know ServiceNow scope keys by heart
and cannot compose on-the-fly queries.

## Goal

Replace the hardcoded area registry with a community-maintained JSON catalog hosted
on GitHub and bundled inside the package. `nexus sync` keeps it current.
Users refer to products by name or acronym; up to two products can be combined
into one ERD.

---

## Data Model

### `ScopeEntry` (replaces `ScopeRef` from deleted `areas.py`)

```
key    str   -- sys_scope.scope value, e.g. "sn_hamp"
label  str   -- human label, e.g. "Hardware Asset Management Pro"
```

### `SchemaProduct`

```
key             str                  -- machine slug: "ham"
acronym         str                  -- short form: "HAM"
name            str                  -- full name: "Hardware Asset Management"
scopes          tuple[ScopeEntry]    -- sys_scope keys to discover
bridge_targets  tuple[str]           -- optional: cross-scope tables used for
                                        narrowing (e.g. ["cmdb_ci"])
                                        products with scopes=[] are bridge-only
```

### `SchemaProductCatalog`

```
version   str                      -- "1.0"; reserved for future schema evolution
products  tuple[SchemaProduct]
```

All models: `frozen=True, strict=True, extra="forbid"`.

### Bundled catalog (`src/nexus/schema/products.json`)

Ships inside the Python package. Contains at minimum:

| key          | acronym      | name                               | scopes       | bridge_targets |
|--------------|--------------|------------------------------------|--------------|----------------|
| ham          | HAM          | Hardware Asset Management          | sn_hamp      | cmdb_ci        |
| itsm         | ITSM         | IT Service Management              | (empty)      | incident, task, change_request, cmdb_ci |
| doc-designer | DOC          | Document Designer                  | sn_grc_doc_design, sn_grc_rel_config | |
| bcm          | BCM          | Business Continuity Management     | sn_bcm, sn_bcm_lite, sn_bcm_map, sn_bcp | |

The "ITSM" entry is bridge-only (no scopes): it represents the set of core global
tables that scoped products connect to. It is invalid to request an ERD for ITSM
alone; it is valid as the second argument to a two-product combination.

---

## ProductRegistry

File: `src/nexus/schema/product_registry.py`

```
load_catalog() -> SchemaProductCatalog
    Reads ~/.nexus/schema/catalog.json when present.
    Falls back to the bundled products.json via importlib.resources.
    Never raises -- always returns a valid catalog.

save_catalog(catalog, source) -> None
    Atomic write via tempfile + rename (same pattern as TemplateRegistry).
    Writes to ~/.nexus/schema/catalog.json.

resolve(ref: str) -> SchemaProduct | None
    Case-insensitive match against key, acronym, and name.
    Returns None when no match found.
```

---

## Sync Integration

### New files

- `src/nexus/schema/sync.py`:
  - `SchemaSyncSource` -- frozen dataclass (repo, branch, path); parallel to
    `SyncSource` in templates but owned by the schema layer to avoid
    cross-layer imports (schema and templates are both layer 5)
  - `GitHubProductCatalogClient` -- anonymous fetcher, mirrors `GitHubTemplateClient`
    but parses `SchemaProductCatalog` instead of `TemplateManifest`
  - `SchemaSync` -- orchestrator, mirrors `GitHubSync`, uses `ProductRegistry`

### `_sync_main` in `commands_sync.py`

Extended to call `SchemaSync.run()` after the existing template sync. The catalog
sync path within the GitHub repo is `schema/products.json` (same repo, same branch).

Both syncs are independent: catalog fetch failure prints a warning but does not
set a non-zero exit code and does not abort the template sync.

Console output after sync:

```
Synced 12 templates from owner/repo@main.
Synced 47 schema products from owner/repo@main.
```

If catalog fetch fails:

```
Synced 12 templates from owner/repo@main.
Warning: schema product catalog sync failed (see log). Using cached or bundled catalog.
```

---

## CLI Changes

### `nexus schema erd`

Old signature:
```
nexus schema erd <area>
```

New signature:
```
nexus schema erd <product> [product2]
```

- `product` and `product2` each accept key, acronym, or full name (case-insensitive)
- All existing flags (`--image`, `--output`, `--grouped`, `--save-archive`,
  `--from-archive`, `--kroki-url`, `--kroki-timeout`) unchanged

Combination rules:

| product          | product2         | behaviour                                           |
|------------------|------------------|-----------------------------------------------------|
| scoped           | absent           | discover product scopes, apply bridge_targets       |
| scoped           | scoped           | union of both scope sets, union of bridge_targets   |
| scoped           | bridge-only      | product scopes + product2 bridge_targets as targets |
| bridge-only      | scoped           | product2 scopes + product bridge_targets as targets |
| bridge-only      | bridge-only      | error: cannot combine two bridge-only products      |
| bridge-only      | absent           | error: product X has no discoverable scopes         |

`SchemaArea` is built on the fly from the resolved product(s):

```python
SchemaArea(
    key=combined_key,
    display=combined_display,
    scopes=tuple(ScopeEntry(key=e.key, label=e.label) for e in combined_scopes),
    bridge_targets=combined_bridge_targets,
)
```

`SchemaDiscoverer` and all layers below the CLI never import from `products.py`.

### `nexus schema areas` renamed to `nexus schema products`

Output includes key, acronym, name, scope keys, bridge targets, and a footer:
`(bundled)` or `(synced YYYY-MM-DD HH:MM UTC)`.

---

## Migration

### Deleted
- `src/nexus/schema/areas.py`

### Added
- `src/nexus/schema/products.py` -- models
- `src/nexus/schema/product_registry.py` -- registry
- `src/nexus/schema/products.json` -- bundled catalog
- `src/nexus/schema/sync.py` -- sync client + orchestrator + SchemaSyncSource

### Modified
- `src/nexus/schema/models.py` -- absorb `SchemaArea` + `ScopeRef` (as `ScopeEntry`)
- `src/nexus/cli/commands_schema.py` -- product resolution, 1-2 product handling
- `src/nexus/cli/commands_sync.py` -- call SchemaSync, report both results
- `src/nexus/schema/__init__.py` -- update exports
- `pyproject.toml` -- add `products.json` to package includes

---

## Tests

### `tests/schema/test_schema_products.py` (replaces `test_schema_areas.py`)

- `test_schema_product_catalog_resolves_by_key`
- `test_schema_product_catalog_resolves_by_acronym`
- `test_schema_product_catalog_resolves_by_name`
- `test_schema_product_catalog_resolve_unknown_returns_none`
- `test_schema_product_catalog_bundled_contains_expected_products`

### `tests/schema/test_schema_product_registry.py`

- `test_product_registry_save_then_load_roundtrip`
- `test_product_registry_load_falls_back_to_bundled_when_cache_absent`
- `test_product_registry_atomic_write_leaves_old_cache_on_failure`

### `tests/schema/test_schema_sync.py`

- `test_github_product_catalog_client_returns_catalog_on_200`
- `test_github_product_catalog_client_returns_none_on_404`
- `test_schema_sync_run_ok_caches_catalog`
- `test_schema_sync_run_fetch_failed_preserves_existing_cache`

### `tests/cli/test_commands_schema.py` additions

- `test_schema_erd_resolves_product_by_acronym`
- `test_schema_erd_two_products_union_scopes`
- `test_schema_erd_two_bridge_only_products_errors`
- `test_schema_products_command_shows_bundled_source_when_no_sync`

### Fakes (`tests/fakes/`)

- `FakeProductRegistry` -- in-memory catalog, injectable
- `FakeGitHubProductCatalogClient` -- returns canned `SchemaProductCatalog | None`

---

## Out of Scope

- Schema diff (`nexus schema diff`) -- separate fast-follow
- More than 2 products in one ERD -- not planned
- Auto-detection of bridge tables from live instance data
