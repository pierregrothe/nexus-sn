# Plugin Multi-Baseline Drift -- Design Spec

**Sub-project:** L
**Status:** Approved for implementation
**Date:** 2026-05-12
**Author:** Pierre Grothe
**Branch:** `feat/plugins-multi-baseline-drift` (from `main` at SHA `fbb130a`)

## Goal

Replace the single-file baseline (`plugins.baseline.json`) with a
directory of named baselines. Users can `--ack` multiple snapshots
under chosen names (e.g., `pre-upgrade`, `quarterly-prod`) and run
drift against any of them.

## Non-Goals

- Cross-profile baselines. Baselines remain scoped to one instance.
- Baseline retention policy / TTL. Pre-release tool; defer auto-cleanup.
- Baseline metadata (description, tags). The name + captured_at suffice.
- Diff of two baselines (use `nexus plugins diff` between live
  inventories on different profiles, not a separate command).

## Architecture

The baseline file moves from a single path to a per-name directory:

```
~/.nexus/instances/<profile>/
    plugins.baseline.json           (old; invalidated on load)
    baselines/
        default.json                (new -- previous default)
        pre-upgrade-xanadu.json     (user-named)
        quarterly-prod.json         (user-named)
```

The drift module is unchanged -- it still compares two
`PluginInventory` values. Only the registry layer and the CLI gain
name parameters.

## Naming Rules

Baseline names must match `^[a-z0-9][a-z0-9_-]{0,62}$`:

- Lowercase ASCII letters, digits, hyphens, underscores
- Must start with a letter or digit
- Maximum 63 characters

Helper: `validate_baseline_name(name: str) -> None` raises
`InvalidBaselineNameError` on violation. Used at every CLI boundary.

Constant: `DEFAULT_BASELINE_NAME = "default"`.

## Components

### 1. `src/nexus/plugins/baselines.py` (new)

Pure name-validation helper module. Owns the regex constant and the
validator function. Re-exported from `nexus.plugins`.

```python
DEFAULT_BASELINE_NAME = "default"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


def validate_baseline_name(name: str) -> None:
    """Raise ``InvalidBaselineNameError`` if name violates the safe-filename rule."""
```

### 2. `src/nexus/plugins/errors.py`

Add `InvalidBaselineNameError(name)` and `BaselineNotFoundError(profile, name)`.

`PluginBaselineNotFoundError` (existing) gets one new field `name: str`
so it can also signal "no such named baseline". Or: keep it as
"no baseline at all" and add a separate `BaselineNotFoundError` for the
named case. Plan picks the latter -- the existing class kept for the
"profile has no baselines directory at all" case.

### 3. `src/nexus/instances/registry.py`

Replace the single `load_plugin_baseline` / `save_plugin_baseline` pair
with name-parameterized versions:

```python
def load_plugin_baseline(self, profile: str, name: str) -> PluginInventory | None: ...
def save_plugin_baseline(self, profile: str, name: str, inventory: PluginInventory) -> None: ...
def list_plugin_baselines(self, profile: str) -> tuple[str, ...]: ...
def delete_plugin_baseline(self, profile: str, name: str) -> None: ...
```

`load_plugin_baseline` returns `None` for missing files (matches existing
behaviour); raises `InstanceNotFoundError` for missing profile.

`save_plugin_baseline` creates the `baselines/` directory if absent;
writes `<name>.json` atomically.

`list_plugin_baselines` returns `tuple` of names sorted ascending; empty
tuple when no baselines exist.

`delete_plugin_baseline` raises `BaselineNotFoundError` when the named
file does not exist.

### 4. Legacy migration

On *any* call to `load_plugin_baseline`, `list_plugin_baselines`, or
`save_plugin_baseline`, the registry checks for the legacy
`plugins.baseline.json` file. If found, log a one-line WARNING
(`legacy plugins.baseline.json for profile=<x> is ignored; re-ack to
create a named baseline`) and ignore it. Do not auto-migrate -- the file
might have a stale schema from sub-project I. User runs `nexus plugins
drift --ack` to create a new `baselines/default.json`.

### 5. `src/nexus/cli.py`

**`nexus plugins drift`** -- existing command. Add `--baseline <name>`
option, default `DEFAULT_BASELINE_NAME`. The `--ack` flag now writes to
`baselines/<name>.json` instead of `plugins.baseline.json`.

**`nexus plugins baselines list`** -- new subcommand. Renders a
DataTable of `name | captured_at | plugin_count` for each saved baseline.

**`nexus plugins baselines delete <name>`** -- new subcommand. Removes
the named baseline file. Confirms with the user unless `--yes` is set.

## Data Flow

```
Today:
    plugins.baseline.json    -- one file per profile
                            |
    nexus plugins drift     -- compare current vs that one
    nexus plugins drift --ack -- overwrite that one

After L:
    baselines/<name>.json   -- multiple files per profile
                            |
    nexus plugins drift [--baseline NAME]      -- compare against named baseline
    nexus plugins drift --ack [--baseline NAME] -- write/overwrite named baseline
    nexus plugins baselines list               -- enumerate
    nexus plugins baselines delete NAME        -- remove one
```

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| `nexus plugins drift` no baseline named `<name>` | Exit 1 with hint: "run nexus plugins drift --ack --baseline <name>" |
| `--baseline foo` where `foo` is invalid name | Exit 1 with regex hint |
| `nexus plugins baselines delete <name>` not found | Exit 1 |
| Legacy `plugins.baseline.json` present | Log WARNING, ignore; user must re-ack |
| `baselines/` directory missing | Treat as zero baselines |

## Output Examples

`nexus plugins baselines list`:

```
Saved baselines for instance dev12345
=====================================
Name              Captured              Plugins
default           2026-05-10 14:00:00   147
pre-upgrade-xan   2026-05-09 09:30:00   144
```

`nexus plugins drift --baseline pre-upgrade-xan`:

```
Drift between baseline 'pre-upgrade-xan' and current
====================================================
Plugin                  Status            Baseline -> Current
com.snc.discovery       version_changed   1.2.3 -> 1.2.4
com.acme.helper         added             - -> 3.2.0

2 changes (1 version, 1 added)
```

## Testing

- `tests/test_plugins_baselines.py` (new): name validation tests.
- `tests/test_instances_registry.py`: ~6 tests for the new registry methods.
- `tests/test_cli_plugins_drift.py`: update existing tests for the
  `--baseline` flag; default-name compatibility.
- `tests/test_cli_plugins_baselines.py` (new): list / delete subcommand tests.

## Out of Scope

- Re-using `apply_overrides` for baselines (no overlap).
- AI-suggested baseline names. Defer to sub-project E.
- Compressing baselines on disk. Per-file JSON stays uncompressed for
  human inspection.
