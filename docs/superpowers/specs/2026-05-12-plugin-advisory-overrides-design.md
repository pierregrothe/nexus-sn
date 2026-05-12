# Plugin Advisory Overrides -- Design Spec

**Sub-project:** K
**Status:** Approved for implementation
**Date:** 2026-05-12
**Author:** Pierre Grothe
**Branch:** `feat/plugins-advisory-overrides` (from `main` at SHA `806b01b`)

## Goal

Let users defer advisory findings on a per-instance basis. Once an advisory
(EOL / CVE / license) on a specific plugin is marked deferred with a
reason, it stops surfacing in the default `nexus plugins advisories`
output. The override file is reviewable, auditable, and reversible.

## Non-Goals

- Global overrides spanning multiple instances. Risk posture is
  per-instance.
- Time-bound expiration (`expires_at`). YAGNI; can add later if the
  audit story requires it.
- AI-assisted suppression suggestions. That belongs in sub-project E.
- Override at the plugin level (suppress *all* advisories on plugin X).
  Always require the specific finding triple.

## Architecture

One new pure module (`overrides.py`), one new on-disk artifact
(`advisory-overrides.yaml` per profile), three new CLI subcommands,
and one new `--include-deferred` flag on the existing `advisories`
command. The override file is owned by the registry layer, mirroring
the existing inventory/baseline pattern.

```
overrides.py    -- AdvisoryOverride, AdvisoryOverrideSet, apply_overrides
                       |
                       +-> cli.py     -- plugins advisories defer / undo-defer
                                         / list-deferred + --include-deferred
                       +-> registry   -- load_advisory_overrides / save_advisory_overrides
```

## Data Model

### `AdvisoryOverride` (`src/nexus/plugins/overrides.py`)

```python
class AdvisoryOverride(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    plugin_id: str
    advisory_type: AdvisoryType
    details: str
    reason: str
    created_at: UtcDatetime
```

`details` matches the `AdvisoryFinding.details` value exactly (CVE id like
`CVE-2024-1234`, EOL effective-date string, license vendor name).

### `AdvisoryOverrideSet`

```python
class AdvisoryOverrideSet(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    overrides: tuple[AdvisoryOverride, ...]
```

Stable order: `(plugin_id asc, advisory_type asc, details asc)`.

## Match Key

```python
def _key(plugin_id: str, advisory_type: AdvisoryType, details: str) -> tuple[str, str, str]:
    return (plugin_id, advisory_type.value, details)
```

Used by both `_key_from_finding(finding: AdvisoryFinding)` and
`_key_from_override(override: AdvisoryOverride)` so the same tuple
shape backs the lookup set.

## Core Function

```python
def apply_overrides(
    advisories: AdvisorySet,
    overrides: AdvisoryOverrideSet,
) -> tuple[AdvisorySet, tuple[AdvisoryFinding, ...]]:
    """Split findings into (remaining, deferred).

    Returns:
        (remaining_advisory_set, deferred_findings) where:
        - remaining: AdvisorySet whose findings do not match any override key
        - deferred: tuple of findings filtered out, in their original sort order
    """
```

`apply_overrides` is pure and side-effect free. The CLI applies it to the
output of `compute_advisories` before rendering.

## Persistence

Per-profile YAML at `~/.nexus/instances/<profile>/advisory-overrides.yaml`:

```yaml
overrides:
  - plugin_id: com.snc.discovery
    advisory_type: cve
    details: CVE-2024-1234
    reason: Compensating control in place via WAF rule X-42.
    created_at: 2026-05-12T10:00:00+00:00
```

Registry methods (added to `InstanceRegistry`):

- `load_advisory_overrides(profile: str) -> AdvisoryOverrideSet` (returns
  empty set when file is absent; raises `InstanceNotFoundError` on bad
  profile; on `ValidationError`, logs WARNING with refresh hint and
  returns the empty set).
- `save_advisory_overrides(profile: str, overrides: AdvisoryOverrideSet) -> None`
  -- atomic-write via the existing `_atomic_write` helper, using
  `yaml.safe_dump` for output.

## CLI Surface

### New subcommand: `nexus plugins advisories defer`

```
nexus plugins advisories defer <plugin_id> <advisory_type> <details> --reason "..."
```

- `plugin_id`: positional, the SN plugin id
- `advisory_type`: positional, one of `eol|cve|license`
- `details`: positional, the exact `AdvisoryFinding.details` string
- `--reason`: required string
- `--instance`: optional profile selector (default: configured default)

Behaviour: load current overrides, verify there is no duplicate, verify a
matching finding currently exists in `compute_advisories` output (so
users do not accidentally store overrides for non-existent advisories),
append the new entry with `created_at=datetime.now(UTC)`, save.

Exit codes:
- `0`: override added
- `1`: duplicate override, no matching finding, or input validation error

### New subcommand: `nexus plugins advisories undo-defer`

```
nexus plugins advisories undo-defer <plugin_id> <advisory_type> <details>
```

Behaviour: load, drop the matching override, save. Exit code `1` when no
matching override exists.

### New subcommand: `nexus plugins advisories list-deferred`

```
nexus plugins advisories list-deferred [--format text|json]
```

Renders the override set as a table (or JSON dump) sorted by
`(plugin_id, advisory_type, details)`. Includes `reason` and
`created_at` columns. Empty set prints `No advisory overrides`.

### Modified: `nexus plugins advisories --include-deferred`

Adds a flag that, when set, includes deferred findings in the normal
output marked with a `[deferred]` prefix in the summary cell. Default
behaviour (flag absent) excludes them.

The default summary line gains a `; N deferred` suffix when any
overrides matched. Example: `5 findings (2 critical, 3 high); 1 deferred`.

## Errors

New error in `src/nexus/plugins/errors.py`:

```python
class AdvisoryOverrideError(Exception):
    """Raised by the CLI override subcommands on user-input failure.

    Attributes:
        plugin_id: SN plugin identifier referenced by the failed command.
        advisory_type: Advisory type referenced by the failed command.
        details: Finding details string referenced by the failed command.
        reason_code: One of 'no_matching_finding', 'duplicate', 'not_found'.
    """
```

The CLI catches this and renders a user-friendly message.

## Output Examples

`nexus plugins advisories` (with one deferred CVE):

```
CVE advisories
==================================================
Plugin               Severity   Summary
com.snc.discovery    high       Authn bypass
...

3 findings (1 critical, 2 high); 1 deferred
```

`nexus plugins advisories --include-deferred`:

```
CVE advisories
==================================================
Plugin               Severity   Summary
com.snc.discovery    high       Authn bypass
com.acme.helper      medium     [deferred] XSS (CVE-2024-1234)
...

4 findings (1 critical, 2 high, 1 medium); 1 deferred
```

`nexus plugins advisories list-deferred`:

```
Plugin             Type   Details          Reason                       Created
com.acme.helper    cve    CVE-2024-1234    Compensating control...      2026-05-12
```

## Testing

- `tests/test_plugins_overrides.py`: ~10 tests covering
  `apply_overrides` (empty / one match / no match / multi-match per
  plugin / preserves order / round-trip JSON).
- `tests/test_cli_plugins_advisories_defer.py`: ~8 tests for the three
  new subcommands and the `--include-deferred` flag.
- `tests/test_instances_registry.py`: 4 tests for
  `load_advisory_overrides` / `save_advisory_overrides`
  (missing file, round-trip, schema-mismatch invalidation,
  profile-not-found).

## Out of Scope

- Schema versioning for `advisory-overrides.yaml`. Pre-release tool;
  follow the same `ValidationError -> WARN + treat as empty` policy used
  for `plugins.json` invalidation in sub-project I.
- Bulk import / export of overrides between profiles. Defer.
- Expiry / re-review reminders. Defer; tracked in roadmap as a future
  enhancement once override volume justifies it.
