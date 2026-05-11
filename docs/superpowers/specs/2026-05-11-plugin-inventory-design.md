# Plugin Inventory Design

Date: 2026-05-11
Status: approved, ready for implementation plan
Sub-project A of the plugin management roadmap (6 sub-projects total).

## Goal

Give NEXUS the ability to read, store, filter, and export the list of
ServiceNow plugins installed on a registered instance. This is the read-only
foundation that every other plugin management capability (cross-instance diff,
update detection, health audit, AI recommendations, governance) builds on.

## Non-goals

- Activating, deactivating, or upgrading plugins. The Table API does not expose
  an activation endpoint; that is a sub-project C concern with caveats.
- Cross-instance plugin diff. Belongs in sub-project B.
- Update detection or release-note pull. Belongs in sub-project C.
- Plugin dependency-tree traversal with cycle detection. Sub-project A stores
  the direct `depends_on` list; traversal/visualization is sub-project B.

## Architecture

### Layer placement

New top-level module `src/nexus/plugins/` sits alongside `capture/` and
`assessment/`. It imports from `cache/`, `config/`, `connectors/`, and
`instances/` only -- never from `cli`, `ui`, `agents`, or `execution`. The
layer-dependency rule in `.primer/patterns.md` is preserved.

```
src/nexus/plugins/
  __init__.py              -- __all__ re-exports
  models.py                -- PluginInfo, PluginInventory, ProductFamily
  scanner.py               -- PluginScanner: async REST -> PluginInventory
  product_families.py      -- loader for product_families.yaml
  product_families.yaml    -- curated plugin_id -> product mapping (data file)
  errors.py                -- PluginScanError (extends NexusError)
```

### Data source

Read two ServiceNow tables and dedupe:

- `v_plugin` -- legacy plugin records. Most reliable on pre-Tokyo instances.
  Fields used: `name`, `id`, `version`, `active`, `description`,
  `dependencies`, `sys_id`, `installed_on`.
- `sys_store_app` -- Store apps + scoped apps + modern plugins on Yokohama+.
  Fields used: `name`, `scope`, `version`, `active`, `vendor`, `dependencies`,
  `sys_id`, `sys_created_on`.

Dedup key: `scope` (sys_store_app) or `id` (v_plugin). When the same plugin
appears in both tables (Yokohama+ duplicates between the legacy view and the
new store table), the `sys_store_app` record wins because it carries vendor
information used to derive `source`.

`source` derivation:

- `sys_store_app.vendor in {"ServiceNow", "Service-now.com"}` -> `"servicenow"`
- `sys_store_app.vendor` present, non-ServiceNow -> `"store"`
- record only in `v_plugin` with no `sys_store_app` row -> `"servicenow"`
- scope starting with `x_` or `u_` -> `"custom"`

### Pydantic models

`src/nexus/plugins/models.py` defines three frozen models:

```python
class PluginInfo(BaseModel):
    """One plugin's static metadata on an instance."""
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    plugin_id: str                          # e.g. "com.snc.incident"
    name: str                               # display name
    version: str                            # installed version
    state: Literal["active", "inactive"]
    source: Literal["servicenow", "store", "custom"]
    product_family: str                     # from curated YAML
    depends_on: tuple[str, ...]             # direct dependencies only
    sys_id: str
    installed_at: UtcDatetime | None        # active_set_on / sys_created_on


class PluginInventory(BaseModel):
    """Full inventory captured at one moment in time."""
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    captured_at: UtcDatetime
    sn_version: str
    plugins: tuple[PluginInfo, ...]


class ProductFamily(StrEnum):
    """Product taxonomy used for filtering."""
    ITSM = "ITSM"
    ITOM = "ITOM"
    ITAM = "ITAM"
    SPM = "SPM"
    CSM = "CSM"
    HRSD = "HRSD"
    FSM = "FSM"
    GRC = "GRC"
    IRM = "IRM"
    SEC_OPS = "SecOps"
    PLATFORM = "Platform"
    UNCATEGORIZED = "Uncategorized"
```

### Product-family curation

`product_families.yaml` is a flat mapping:

```yaml
"com.snc.incident":          ITSM
"com.snc.problem":           ITSM
"com.snc.change_management": ITSM
"com.snc.discovery":         ITOM
"sn_hr_core":                HRSD
"sn_customerservice":        CSM
# ... ~50 initial entries
```

The loader caches the dict at import time and exposes
`product_family_for(plugin_id: str) -> ProductFamily`. Unknown IDs return
`ProductFamily.UNCATEGORIZED`. The YAML schema is validated at load time
against a Pydantic `ProductFamilyMap` model so a typo in the file fails fast
with a clear error rather than silently mis-tagging plugins.

### Integration with instance refresh

The existing `InstanceScanner` (in `src/nexus/instances/scanner.py`) currently
returns an `InstanceSnapshot` of AI Skills / Flows / Business Rules / Script
Includes. It gains:

- A new `PluginScanner` collaborator that takes an open
  `ServiceNowClient` and returns a `PluginInventory`.
- `InstanceScanner.scan()` calls both scans concurrently with
  `asyncio.gather()`.
- `nexus instance refresh` writes `plugins.json` to the instance directory
  alongside `meta.json` and `snapshot.json`.

`InstanceMeta.snapshot_counts` gains a `plugins: int = 0` field so
`nexus instance status` shows the plugin count next to the artifact counts.

The `plugins.json` file is loaded by `InstanceRegistry.load_plugin_inventory(profile)`,
which returns `PluginInventory | None`. None when the file does not exist (instance
registered but never refreshed since this feature shipped) or when the JSON is
unparseable.

### CLI surface

A new `nexus plugins` sub-app, mirroring the `nexus instance` and
`nexus capture` patterns.

```
nexus plugins                          -- callback: 'plugins list' + CommandGuide
nexus plugins list [--instance P]      -- DataTable: ID, Name, Version, State, Source, Product
       [--product ITSM]                   -- filter by product family
       [--source servicenow|store|custom] -- filter by source
       [--state active|inactive]          -- filter by activation state
nexus plugins info <plugin_id> [--instance P]
                                       -- KeyValuePanel with full PluginInfo
                                          plus Hint listing direct dependencies
nexus plugins export [--instance P]    -- write inventory to file
       [--format yaml|csv]                -- default yaml
       [--out FILE]                       -- default plugins.<ext> in cwd
```

All commands resolve their instance via the existing `_resolve_profile`
helper; the `--instance` flag is optional and defaults to the configured
default profile. When `plugins.json` is missing or empty, every command
prints `Notice.warn("Plugin inventory empty.")` followed by
`Hint(label="Refresh", command="nexus instance refresh")`.

### Reuse from existing layers

- `ServiceNowClient` (connectors) handles auth, retry, pagination.
- `_resolve_profile` (cli.py) resolves the optional `--instance` flag.
- `DataTable` / `KeyValuePanel` / `Notice` / `CommandGuide` / `Hint` from the
  freshly-shipped `nexus.ui` library render every output. No new Rich code in
  `cli.py`.
- `_clear_cache` semantics already apply: if a future sub-project caches
  derived plugin views, they will use the same `@cached` decorator pattern.

### Errors

`PluginScanError(NexusError)` raised by `PluginScanner.scan()` when neither
`v_plugin` nor `sys_store_app` is readable. Caught by `nexus instance refresh`
and surfaced as a Notice.error, but the rest of the snapshot still saves --
plugin scan failure must not block artifact capture.

## Testing strategy

All tests use real fakes per the project's no-mocks rule.

- `tests/fakes/fake_plugin_data.py` -- canned row tuples for `v_plugin`,
  `sys_store_app`, including one dedup case, one custom-scope case, one
  inactive plugin, one plugin in YAML and one not.
- `tests/test_plugins_models.py` -- Pydantic round-trip, frozen enforcement,
  Literal validation.
- `tests/test_plugins_product_families.py` -- YAML loads cleanly, every entry
  maps to a valid `ProductFamily`, no duplicate keys, unknown ID returns
  `UNCATEGORIZED`.
- `tests/test_plugins_scanner.py` -- scan with fake transport. Asserts dedup,
  source derivation rules, state mapping, dependencies parsing.
- `tests/test_instances_scanner.py` -- additional cases asserting plugin scan
  runs concurrently with artifact scan and writes `plugins.json`.
- `tests/test_cli_plugins.py` -- CliRunner against a fake snapshot with two
  registered instances. Asserts:
  - `nexus plugins list` shows all plugins.
  - Each filter flag narrows correctly.
  - `nexus plugins info <unknown>` exits non-zero with Notice.error.
  - `nexus plugins export --format csv` writes a parseable CSV.
  - `nexus plugins export --format yaml` round-trips through PluginInventory.

Test naming follows `test_<function>_<scenario>`.

## File layout

New files (creating):

```
src/nexus/plugins/
  __init__.py
  models.py
  scanner.py
  product_families.py
  product_families.yaml
  errors.py

tests/
  test_plugins_models.py
  test_plugins_product_families.py
  test_plugins_scanner.py
  test_cli_plugins.py

tests/fakes/
  fake_plugin_data.py
```

Modified files:

```
src/nexus/cli.py                        -- new plugins_app + 4 commands
src/nexus/instances/scanner.py          -- call PluginScanner concurrently
src/nexus/instances/registry.py         -- load_plugin_inventory + save_plugin_inventory
src/nexus/instances/models.py           -- snapshot_counts.plugins field
src/nexus/ui/__init__.py                -- no change; UI components already exported
.ratchet.json                           -- new module entries
```

## Risks

- **SN version drift.** Older PDIs may lack `sys_store_app` and rely entirely
  on `v_plugin`. Mitigation: scanner treats either-table failure as
  "fall back to the other one" rather than hard failure.
- **Curated YAML staleness.** New plugins ship with each SN release. Mitigation:
  the unknown-ID path is a soft fallback (`Uncategorized`), not an error.
  Roadmap item: a quarterly review action on the YAML.
- **Plugin scan cost.** Two tables, possibly large (~500 plugins on a mature
  instance). Mitigation: paginate at `sysparm_limit=200` and run both queries
  concurrently inside `_scan_plugins`. Bounded by SN's max page count.

## Out of scope (deferred)

- Dependency-tree visualization (sub-project B).
- Available-version detection / update workflow (sub-project C).
- Orphaned / deprecated / CVE / license checks (sub-project D).
- AI recommendations (sub-project E).
- Activation audit history (sub-project F).

## Open questions

None remain after the brainstorm. The dependency-tree visualization choice
(keep simple direct-list now vs. full traversal in A) was resolved by
deferring traversal to sub-project B.
