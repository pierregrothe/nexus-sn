# NEXUS Plugin Drift Detection -- Design

**Status:** approved
**Date:** 2026-05-12
**Sub-project:** H (follows G plugin cleanups, PR #18)
**Spec author:** Claude Opus 4.7 with Pierre Grothe

## Summary

Detect plugin changes on a single ServiceNow instance between an
explicit baseline snapshot and the current snapshot. Audit-focused:
surfaces unauthorized plugin installs, removals, version bumps, and
state flips between the time a user marks a baseline (`drift --ack`)
and the time they run the drift check.

Cross-instance comparison is already shipped (`nexus plugins diff`
from sub-project C). This sub-project complements it with a
single-instance-over-time view.

## Goals

- **Audit visibility.** Tell the user "what changed since the last
  baseline." No silent advance, no lost drift.
- **Explicit baseline.** The user consciously establishes what
  "known good" means via `nexus plugins drift --ack`.
- **CI-friendly.** `--format json` for parseable output, `--strict`
  for non-zero exit on any drift.
- **Surgical scope.** Mirror the four `PluginDiff` statuses (added,
  removed, version_changed, state_changed). No record-count drift,
  no time-series history.

## Non-goals

- Time-series history of all snapshots over time (forensics use case).
  If the audit case proves valuable, sub-project I can add history.
- Record-count drift detection. Too noisy for audit (record counts
  change with normal user activity).
- Cross-instance drift. Already shipped as `nexus plugins diff`.
- Automated alerting / notifications. CLI exit codes via `--strict`
  give CI scripts the hook they need; alerting is the script's job.

## Use case

```
2026-05-01: nexus instance refresh prod    -> plugins.json captured
2026-05-01: nexus plugins drift --ack      -> plugins.baseline.json written
2026-05-08: someone activates com.snc.questionable on prod (outside CR)
2026-05-12: nexus instance refresh prod    -> plugins.json updated
2026-05-12: nexus plugins drift            -> reports state_changed: com.snc.questionable inactive -> active
2026-05-12: (user investigates, takes action)
2026-05-13: nexus plugins drift --ack      -> baseline advances to current state
```

CI:

```
nexus plugins drift --strict --format json --instance prod
# exit 0 + empty entries if no drift
# exit 1 + JSON report if drift detected
```

## Architecture

### Storage

One new file per profile, alongside the existing `plugins.json`:

```
<config_dir>/instances/<profile>/
  meta.json
  plugins.json           # current snapshot (existing, every refresh overwrites)
  plugins.baseline.json  # baseline snapshot (NEW, written only by drift --ack)
  snapshot.json          # instance counts (existing)
```

`plugins.baseline.json` has the same `PluginInventory` JSON shape as
`plugins.json`. Same Pydantic model, same serialization. The two
files are independent: refresh never touches the baseline.

### Domain model (`src/nexus/plugins/drift.py`)

New module, mirror of `diff.py`'s structure. Two Pydantic models +
one pure function. No I/O.

```python
class PluginDriftEntry(BaseModel):
    """One drift row: how a plugin changed between baseline and current.

    Attributes:
        plugin_id: Canonical SN plugin identifier.
        name: Display name (from whichever inventory had the entry).
        product_family: Curated product family or "Uncategorized".
        status: Why this row appears.
        baseline_version: Version in baseline, or None when added.
        current_version: Version in current, or None when removed.
        baseline_state: State in baseline, or None when added.
        current_state: State in current, or None when removed.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    plugin_id: str
    name: str
    product_family: str
    status: Literal["added", "removed", "version_changed", "state_changed"]
    baseline_version: str | None
    current_version: str | None
    baseline_state: Literal["active", "inactive"] | None
    current_state: Literal["active", "inactive"] | None


class PluginDriftReport(BaseModel):
    """Drift between a baseline and current inventory for one profile.

    Attributes:
        profile: Instance profile this drift applies to.
        baseline_captured_at: When the baseline inventory was captured.
        current_captured_at: When the current inventory was captured.
        entries: Drift entries in stable (product_family, plugin_id) order.
    """

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    profile: str
    baseline_captured_at: UtcDatetime
    current_captured_at: UtcDatetime
    entries: tuple[PluginDriftEntry, ...]


def compute_drift(
    baseline: PluginInventory,
    current: PluginInventory,
    profile: str,
) -> PluginDriftReport:
    """Build a drift report from two inventories of the same profile."""
```

Status logic (mirrors `compute_diff` from `diff.py`):

- `plugin_id` in current and not in baseline -> `added`
- `plugin_id` in baseline and not in current -> `removed`
- Same `plugin_id`, different `version` -> `version_changed`
- Same `plugin_id`, different `state` -> `state_changed`
- If both version AND state changed, emit ONE entry with `status=version_changed`
  AND populate baseline_state/current_state truthfully. The text/JSON renderer
  surfaces both deltas via the four fields; status is a categorical primary key,
  not an exhaustive change list.

Sort: stable `(product_family, plugin_id)` ascending.

### Errors (`src/nexus/plugins/errors.py`)

```python
class PluginBaselineNotFoundError(Exception):
    """Raised when nexus plugins drift runs without a saved baseline.

    Profile has no plugins.baseline.json. User must run
    `nexus plugins drift --ack` to mark the current snapshot as the
    baseline first.
    """
```

### Registry (`src/nexus/instances/registry.py`)

Two new methods next to the existing `load_plugin_inventory` /
`save_plugin_inventory`:

```python
def load_plugin_baseline(self, profile: str) -> PluginInventory | None:
    """Read plugins.baseline.json for a profile if it exists.

    Returns:
        PluginInventory, or None if the baseline file does not exist.

    Raises:
        InstanceNotFoundError: If the profile directory does not exist.
    """

def save_plugin_baseline(self, profile: str, inventory: PluginInventory) -> None:
    """Atomically write plugins.baseline.json for a profile.

    Same atomic-rename pattern as save_plugin_inventory.

    Raises:
        InstanceNotFoundError: If the profile directory does not exist.
    """
```

Both reuse the existing tmp-file-and-rename pattern from
`save_plugin_inventory`. Same JSON-encoding via Pydantic's
`model_dump_json`.

### CLI (`src/nexus/cli.py`)

One new command: `plugins_drift`. Flags follow the G convention
established by sub-project G (--format, --strict).

```python
@plugins_app.command("drift")
def plugins_drift(
    instance: Annotated[
        str,
        typer.Option("--instance", help="Instance profile (default: configured default)"),
    ] = "",
    ack: Annotated[
        bool,
        typer.Option(
            "--ack",
            help="Set the current snapshot as the new baseline and exit.",
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: text | json (default: text)"),
    ] = "text",
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Exit with code 1 if any drift is detected after filters.",
        ),
    ] = False,
) -> None:
    """Show plugin drift on an instance since the last baseline."""
```

Two top-level branches:

**`--ack` mode:**
1. `_validate_format(output_format)` -- still validate even though no JSON output.
2. Load current via `_load_inventory_or_exit(instance)` -- exits 1 if absent.
3. `registry.save_plugin_baseline(meta.profile, current)`.
4. Print `Notice.info(f"Baseline set: {N} plugins captured {captured_at}.")` and exit 0.

**Default mode (drift report):**
1. `_validate_format(output_format)`.
2. Load current via `_load_inventory_or_exit(instance)`.
3. Load baseline via `registry.load_plugin_baseline(meta.profile)`.
4. If baseline is None: print error notice + Hint to `nexus plugins drift --ack`, exit 1.
5. `report = compute_drift(baseline, current, meta.profile)`.
6. If `--format json`: `_emit_json(report)`, then `if strict and report.entries: Exit(1)`, return.
7. If `report.entries` empty: print "No drift detected." and return (text only).
8. Render DataTable + summary Notice.
9. If `strict and report.entries: Exit(1)`.

### --strict + --format json interaction

Same pattern as `nexus plugins advisories --strict --format json` from
sub-project G: JSON is emitted to stdout via `_emit_json` (line-buffered
`print()`), then `typer.Exit(1)` fires. JSON reaches stdout cleanly
because `print()` flushes before the exception propagates.

### Layer dependency order

Follows the existing NEXUS layering:

```
nexus.plugins.drift           (pure functions, models)
  depends on:
    nexus.plugins.models      (PluginInventory, PluginInfo)
    nexus.plugins.errors      (PluginBaselineNotFoundError)
    nexus.config.types        (UtcDatetime)

nexus.instances.registry      (storage I/O)
  reuses:
    nexus.plugins.models

nexus.cli                     (CLI plumbing)
  reuses everything above
```

`drift.py` has no imports from `scanner.py`, `impact.py`, `advisories.py`,
`orphans.py`, or `updates.py`. It is a sibling to `diff.py` and identical
in shape.

## Behavior table

| State                                          | `drift` no flags          | `drift --ack`            | `drift --strict`              | `drift --format json`              |
| ---------------------------------------------- | ------------------------- | ------------------------ | ----------------------------- | ---------------------------------- |
| No current snapshot                            | Exit 1 with refresh hint  | Exit 1 with refresh hint | Exit 1 with refresh hint      | Exit 1 with refresh hint           |
| Current exists, no baseline                    | Exit 1 with ack hint      | Sets baseline, exit 0    | Exit 1 with ack hint          | Exit 1 with ack hint               |
| Baseline + current, no drift                   | "No drift detected.", 0   | Advances baseline, 0     | Exit 0                        | `{"entries":[]}`, exit 0           |
| Baseline + current, drift                      | Render report, exit 0     | Advances baseline, 0     | Render + exit 1               | JSON report, exit 1                |

Note: `--ack` does NOT report drift before advancing. If the user wants
to inspect before ack'ing, they run `drift` first, review, then `drift
--ack`. Two-step workflow is intentional.

## Test strategy

- `tests/test_plugins_drift.py` (new) -- pure-function tests for `compute_drift`:
  - All four status cases individually
  - Empty-vs-empty -> no entries
  - Identical -> no entries
  - Mixed: added + removed + version_changed in one report
  - Both version and state changed -> single entry with `status=version_changed`,
    both baseline_state and current_state populated
  - Stable sort: out-of-order inputs produce stable output
- `tests/test_instances_registry.py` -- add baseline round-trip + missing-file tests:
  - `test_load_plugin_baseline_returns_none_when_missing`
  - `test_save_plugin_baseline_round_trip`
  - `test_save_plugin_baseline_overwrites_existing`
  - `test_load_plugin_baseline_raises_when_profile_missing`
- `tests/test_cli_plugins_drift.py` (new) -- CLI integration tests:
  - `test_drift_errors_when_no_current_snapshot`
  - `test_drift_errors_when_no_baseline_with_hint`
  - `test_drift_ack_sets_baseline`
  - `test_drift_reports_no_drift_when_inventories_identical`
  - `test_drift_renders_added_removed_version_state_changes`
  - `test_drift_emits_json_when_format_flag_provided`
  - `test_drift_errors_on_unknown_format_value`
  - `test_drift_strict_exits_1_when_drift_detected`
  - `test_drift_strict_exits_0_when_no_drift`
  - `test_drift_strict_json_emits_and_exits_1`

Approximately 18-20 new tests total. No mocks -- registry tests use
real tempfiles, CLI tests use the existing `runner`/`_seed`/`_info`
patterns from sub-project G.

## Risks

- **Test isolation:** registry tests depend on tmp_path; baseline file
  must be isolated per-test. Existing fixture pattern handles this.
- **Pydantic schema evolution:** if `PluginInventory` changes shape later,
  `plugins.baseline.json` written with an older schema may fail to load.
  Mitigated by `extra="forbid"` being on the inventory model -- a schema
  change forces a baseline reset, which is the right behavior for an
  audit feature anyway (the baseline should be re-established when the
  data model changes).
- **--ack as a destructive operation:** Overwriting the baseline silently
  is fine here -- it's exactly the documented behavior -- but the user
  may want a confirmation prompt or a `--force` flag if they fat-finger.
  Defer to YAGNI: ship without confirmation, add later if real-world
  usage shows fat-fingers happen.

## Out of scope (intentional)

- Diff between baseline and an arbitrary past snapshot (no history)
- Per-plugin baseline (whole-inventory baseline only)
- Multiple named baselines per profile (one baseline per profile only)
- Baseline expiry / staleness warnings
- Webhook notifications on drift

## File map

**New files:**
- `src/nexus/plugins/drift.py` -- domain model + compute_drift
- `tests/test_plugins_drift.py` -- pure-function tests
- `tests/test_cli_plugins_drift.py` -- CLI integration tests

**Modified files:**
- `src/nexus/plugins/__init__.py` -- export PluginDriftReport, PluginDriftEntry, compute_drift
- `src/nexus/plugins/errors.py` -- add PluginBaselineNotFoundError
- `src/nexus/instances/registry.py` -- add load_plugin_baseline + save_plugin_baseline
- `src/nexus/cli.py` -- add plugins_drift command
- `tests/test_instances_registry.py` -- add baseline round-trip tests
- `.ratchet.json` -- bump coverage for the affected modules (last task)

## Spec self-review

**Placeholder scan:** No "TBD" / "TODO" markers. The `<config_dir>`
placeholder in the storage section refers to the existing
`NexusPaths.instances_dir` -- standard pattern, not a placeholder.

**Internal consistency:** Status set (added/removed/version_changed/
state_changed) consistent between models, compute_drift logic,
behavior table, and test strategy. CLI flag names (--ack, --format,
--strict) consistent throughout. Storage path (`plugins.baseline.json`)
consistent everywhere.

**Scope check:** Single sub-project. ~18-20 new tests, 1 new module,
~4 file modifications, 1 new CLI command. Fits in one PR.

**Ambiguity check:** The "both version AND state changed" case is
explicitly resolved (status=version_changed, all four fields populated).
The "ack with no current snapshot" case is explicitly Exit 1 in the
behavior table.
