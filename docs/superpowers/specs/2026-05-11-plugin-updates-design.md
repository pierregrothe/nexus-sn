# Plugin Update Detection Design

Date: 2026-05-11
Status: approved, ready for implementation plan
Sub-project C of the plugin management roadmap.

## Goal

Detect ServiceNow Store apps that have a newer version available and surface
them in a CLI command. Optionally produce a YAML queue file that
documents the pending updates for an admin to work through in
ServiceNow's Application Manager UI.

This sub-project adds **detection only**. Triggering the actual install
of an update is out of scope; ServiceNow's REST surface does not expose a
clean public endpoint for that, and the documented workflow is a UI
action in the Application Manager.

## Non-goals

- **Triggering / executing the update.** No public REST endpoint. The
  user clicks in SN's Application Manager.
- **Pulling release notes.** The `release_notes` field on
  `sys_store_app` is typically empty for OOTB and Store apps. Not
  feasible.
- **Update history / rollback orchestration.** The existing capture
  layer's `nexus instance refresh` already snapshots pre-update state.
  Sub-project C only nudges the user to run it.
- **Core SN plugin updates** (records that live in `v_plugin` but not
  `sys_store_app`). Their "update" equals an SN release upgrade, not a
  separable plugin update. They will never appear in this command's
  output.

## Architecture

### Layer placement

One new file plus a tiny extension of two existing files:

```
src/nexus/plugins/updates.py          -- NEW, one pure function
src/nexus/plugins/models.py           -- MODIFY: add latest_version to PluginInfo
src/nexus/plugins/scanner.py          -- MODIFY: read latest_version from sys_store_app
src/nexus/plugins/__init__.py         -- MODIFY: re-export the new helper
src/nexus/cli.py                      -- MODIFY: add `nexus plugins updates` subcommand
```

No new layer; no upward imports. The pure function in `updates.py`
imports only from `nexus.plugins.models`.

### Model change

Extend `PluginInfo` in `src/nexus/plugins/models.py` with one field:

```python
class PluginInfo(BaseModel):
    """One plugin's static metadata on an instance."""
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
    latest_version: str | None = None      # NEW
```

Default is ``None``, which means "no newer version is known". This
preserves backward compatibility with existing `plugins.json` files
produced by sub-project A.

### Scanner change

In `src/nexus/plugins/scanner.py`:

- Add `latest_version` to `_STORE_FIELDS`:
  ```python
  _STORE_FIELDS = (
      "sys_id,scope,name,version,latest_version,active,vendor,"
      "dependencies,sys_created_on"
  )
  ```
- In `_from_store`, append:
  ```python
  return PluginInfo(
      ...existing fields...,
      latest_version=str(row.get("latest_version", "")) or None,
  )
  ```
  Reading via `row.get("latest_version", "")` then `or None` collapses
  missing key, empty string, and None into ``None``.
- `_from_v_plugin` leaves `latest_version` at the default ``None``; core
  plugins do not have a separable update lifecycle.

Two new tests in `tests/test_plugins_scanner.py`:

- `test_scan_populates_latest_version_when_present`
- `test_scan_leaves_latest_version_none_when_field_absent`

One fake row in `tests/fakes/fake_plugin_data.py` gets `latest_version`
populated so the dedup case carries an update marker.

### Pure function

`src/nexus/plugins/updates.py`:

```python
# src/nexus/plugins/updates.py
# Cross-version update detection for plugin inventories.
# Author: Pierre Grothe
# Date: 2026-05-11
"""plugins_with_updates: filter an inventory down to plugins with a newer version."""

from nexus.plugins.models import PluginInfo, PluginInventory

__all__ = ["plugins_with_updates"]


def plugins_with_updates(inventory: PluginInventory) -> tuple[PluginInfo, ...]:
    """Return plugins whose latest_version differs from version.

    Filters out:
        - Plugins without ``latest_version`` (typically v_plugin-only
          entries -- core SN plugins).
        - Plugins where ``latest_version == version`` (up to date).

    Returns:
        Plugins sorted by ``(product_family, plugin_id)`` for stable output.
    """
    updates = [
        p for p in inventory.plugins
        if p.latest_version is not None and p.latest_version != p.version
    ]
    updates.sort(key=lambda p: (p.product_family, p.plugin_id))
    return tuple(updates)
```

### CLI surface

```
nexus plugins updates [--instance P]
       [--queue FILE]                 -- also write YAML queue to FILE.
                                         Default value when the flag is
                                         omitted: empty string (no YAML
                                         written). When the user wants
                                         the default-named output, they
                                         pass --queue updates-<profile>.yaml
                                         explicitly. This avoids
                                         silent-file-write surprises and
                                         keeps the typer Option shape
                                         simple: a single str with a
                                         meaningful empty-string default.
```

Decisions on shape:

- A single ``updates`` subcommand with an optional ``--queue`` flag,
  matching how ``nexus plugins export`` takes ``--format`` / ``--out``.
- ``--queue`` always requires an explicit file argument when used. Empty
  argument (the default) means "no file written". This avoids the
  surprise of writing a YAML in cwd just because the user typed
  ``--queue``.

Behaviour:

- Empty inventory (file missing) -> ``Notice.warn`` + ``Hint(label="Refresh",
  command=f"nexus instance refresh {profile}")`` + exit 1. Mirrors
  sub-projects A and B.
- No plugins with updates -> ``Notice.info("Up to date.")`` and return.
- One or more updates ->
  - Render ``DataTable(title="Updates available")`` with columns Plugin
    ID, Name, Product, Current, Latest.
  - Trailing ``Notice.info(f"{n} update(s) available.")``.
- ``--queue FILE`` -> additionally write the YAML payload (see below) and
  print a ``Hint(label="Before applying", command=f"nexus instance
  refresh {profile}")`` to remind the user to capture a pre-update
  snapshot.

### Queue YAML shape

```yaml
instance: prod
captured_at: 2026-05-11T15:30:00+00:00
updates:
  - plugin_id: com.acme.helper
    name: Acme Helper
    product_family: Uncategorized
    current_version: "3.0.0"
    latest_version: "3.1.0"
```

The ``captured_at`` value comes verbatim from ``PluginInventory.captured_at``.
Empty list is never written; the "Up to date" path skips file writes
entirely.

### Reuse from existing layers

- ``PluginInfo`` / ``PluginInventory`` -- consumed unchanged structurally.
- ``InstanceRegistry.load_plugin_inventory`` -- single read per profile.
- ``_resolve_profile`` and ``_load_inventory_or_exit`` -- already exist
  in ``cli.py`` from sub-project B; reused.
- ``DataTable`` / ``DataColumn`` / ``Notice`` / ``Hint`` -- already
  exported from ``nexus.ui``.
- ``_yaml.safe_dump`` -- already used by ``nexus plugins export`` and
  ``nexus plugins promote``.
- ``packaging.version`` -- **not used here**. The check is exact-string
  inequality on ``latest_version`` vs ``version``; SN itself populates
  ``latest_version`` from the Store, so the strings are authoritative
  for "newer". Using packaging.version here would introduce false
  negatives when the Store reports a build-tagged string.

### Errors / edge cases

- Unknown profile -> `InstanceNotFoundError` caught by `_resolve_profile`,
  surfaced as `Notice.error` + `typer.Exit(1)`.
- Missing inventory -> `Notice.warn` + Hint + exit 1 (same as
  sub-project B's `_load_inventory_or_exit`).
- All plugins up to date -> `Notice.info("Up to date.")`, exit 0, no
  file written even with ``--queue``.
- `--queue` not provided or empty -> no file written; only the DataTable
  is rendered.
- `--queue` with an unwritable path -> `OSError` propagates; Typer prints
  a traceback. This is acceptable for a write operation; the user fixes
  the path.

## Testing strategy

All tests use real fakes (project no-mocks rule).

### `tests/test_plugins_models.py` (append)

- `test_plugin_info_accepts_latest_version_field`
- `test_plugin_info_defaults_latest_version_to_none`

### `tests/test_plugins_scanner.py` (append)

- `test_scan_populates_latest_version_when_present`
- `test_scan_leaves_latest_version_none_when_field_absent`

### `tests/test_plugins_updates.py` (new)

- `test_plugins_with_updates_filters_to_only_those_with_newer_latest`
- `test_plugins_with_updates_skips_plugins_without_latest_version`
- `test_plugins_with_updates_skips_plugins_at_latest_version`
- `test_plugins_with_updates_sorts_by_product_then_plugin_id`

### `tests/test_cli_plugins_updates.py` (new)

- `test_plugins_updates_renders_datatable_with_pending_updates`
- `test_plugins_updates_prints_up_to_date_when_all_current`
- `test_plugins_updates_writes_yaml_when_queue_flag_provided`
- `test_plugins_updates_does_not_write_yaml_when_queue_flag_omitted`
- `test_plugins_updates_warns_when_inventory_missing`
- `test_plugins_updates_prints_pre_update_refresh_hint_when_queue_written`

Test naming follows `test_<function>_<scenario>`.

## File layout

New files:

```
src/nexus/plugins/updates.py
tests/test_plugins_updates.py
tests/test_cli_plugins_updates.py
```

Modified files:

```
src/nexus/plugins/models.py            -- add latest_version field on PluginInfo
src/nexus/plugins/scanner.py           -- read latest_version from sys_store_app
src/nexus/plugins/__init__.py          -- re-export plugins_with_updates
src/nexus/cli.py                       -- add `updates` subcommand;
                                          update _PLUGINS_HELP
tests/fakes/fake_plugin_data.py        -- add latest_version to one store row
tests/test_plugins_models.py           -- 2 new tests for the new field
tests/test_plugins_scanner.py          -- 2 new tests for scanner population
.ratchet.json                          -- new module baseline + cli.py bump
```

## Risks

- **`sys_store_app.latest_version` may be stale or empty** depending on
  SN version and Store sync schedule. Behaviour: plugin will appear
  up-to-date even when it isn't. Documented limitation, not a bug.
  Mitigation: the user can also run a full SN-side "Newer Store
  Application version available" Instance Scan to refresh; outside the
  scope of NEXUS.
- **Adding the field to `PluginInfo` requires re-running `nexus instance
  refresh`** for the field to actually populate. Existing snapshots
  written before sub-project C ships will load with
  `latest_version=None` (via the default), meaning no updates are
  reported until the user refreshes. The "Up to date" message in that
  case is honest -- the inventory has no update data -- and the
  pre-update refresh Hint produced by other commands already points
  users at the right action.
- **YAGNI risk on the queue YAML format**: the schema is intentionally
  flat (no `actions` bucketing like sub-project B's promote plan)
  because every entry has identical structure. Adding sections later is
  a non-breaking change.

## Out of scope (deferred)

- Triggering updates from NEXUS. SN exposes no public REST endpoint;
  any attempt would be brittle and version-dependent.
- Release notes. The field is typically empty.
- Cross-instance update comparison (`which instances are behind on which
  plugins?`). Possible follow-on, but the cross-instance data shape is
  already covered by sub-project B's diff command; explicit "behind on
  updates per fleet" is a sub-project D concern (fleet health).
- Scheduled / automated update checks. NEXUS does not run as a daemon;
  the user invokes commands when they want fresh data.

## Open questions

None remain after the brainstorm. CLI shape (single subcommand + flag),
queue YAML structure, scope (detection only), and the
detection-via-`sys_store_app.latest_version` data source were all
resolved before this spec was written.
