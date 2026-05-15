# Plugin Batch Upgrade -- Design Spec

Author: Pierre Grothe
Date: 2026-05-14
Status: Draft (pending user review)
Parent: docs/superpowers/specs/2026-05-13-plugin-execution-design.md
Branch: feat/plugins-batch-upgrade

## Goal

Add an ergonomic batch entry point to upgrade many plugins in one
command. Two filter dimensions supported:

1. By product family (one or more, e.g. `--family ITSM --family ITOM`).
2. By update-pending status (all plugins where `latest_version != version`).

The intent stated by the user: "an option to bring the number of
plugins requiring an update to 0", optionally scoped to one or more
product families.

## Non-goals

- New SN endpoints. (None exist; see Native API section.)
- Bulk deactivate / uninstall. SN platform does not expose those (see
  the parent spec, addendum 2026-05-14e).
- Concurrent upgrades. Sequential keeps the progress UI legible and
  matches SN's tracker-per-op model. Optional concurrency is a
  future enhancement, not v1.
- A new `upgrade-all` command. The work attaches to the existing
  `nexus plugins updates` command -- one logical place per concept.

## Native API research

SN does not expose a batch-upgrade endpoint. Confirmed against
`docs/sn-internal-api-catalog.md` (Zurich PDI, sys_ws_definition +
sys_ws_operation; authoritative for scripted-REST). The
`sn_appclient/appmanager` namespace has exactly four ops:

- `GET /app_info_from_store/{sourceAppId}/{version}`
- `GET /progress/{trackerId}`
- `POST /apps`
- `POST /plugins`

Plus the action endpoints used by the existing executor
(`/appmanager/install`, `/upgrade`, `/activate`) -- each is per-plugin
and spawns its own tracker.

`/api/now/v1/batch` (OOB SN batch wrapper) is already used inside
`SNClient.submit_*` to issue one kickoff request, but the resulting
work is still one tracker per plugin. There is no SN-side fan-out.

Result: **the batch is a client-side loop**. We submit per plugin,
poll per plugin, aggregate. This matches the parent spec's executor
design exactly.

## User stories

1. As an admin, I want `nexus plugins updates --apply` to upgrade
   every plugin whose `latest_version` differs, and to keep going
   when individual plugins fail.
2. As an admin, I want `nexus plugins updates --family ITOM
   --family ITSM --apply` to scope the batch to the families I care
   about.
3. As an admin running CI, I want a structured `--out report.yaml`
   so the result is machine-readable and exit code reflects success.
4. As an admin, I want unknown family names to fail loudly and tell
   me which families exist on this instance.

## Decisions

### Family source -- reuse existing taxonomy

`PluginInfo.product_family: str` is already populated for every
plugin via `product_family_for()` (curated YAML + keyword rules +
`com.glide.*` fallback to `PLATFORM`, otherwise `UNCATEGORIZED`).
Filtering is a pure in-memory predicate. No new fields, no new SN
calls.

`--family` accepts the enum member values exactly (`ITSM`, `ITOM`,
`ITAM`, `SPM`, `CSM`, `HRSD`, `FSM`, `GRC`, `IRM`, `SecOps`,
`Platform`, `Uncategorized`). Matching is case-insensitive against
`p.product_family.lower()`. Unknown family name -> exit 2, print
the list of families actually present in the current inventory with
plugin counts, no upgrades attempted.

Available families surfaced via the existing `nexus plugins list
--by-family` style output is sufficient; no new `nexus plugins
families` subcommand needed (YAGNI).

### Skip-on-fail semantics

Batch upgrade uses **skip-on-fail**, never rollback. This is a
deliberate departure from `apply_plan`'s abort+rollback semantics
because the audiences differ:

- `apply_plan` -- cross-instance promotion. Whole plan is a
  transaction; partial state is wrong. Abort + rollback.
- batch upgrade -- routine maintenance over independent
  upgrades. Each plugin is independent; rolling back successful
  upgrades because one failed is destructive and surprising.

When an upgrade fails, the result is recorded with `success=False`
and a reason string, and the loop continues with the next plugin.

### Impact gate (none, by design)

`upgrade` in the existing executor does NOT pass through the
impact gate. Impact gating is gated on deactivate/uninstall (where
data loss is possible). Upgrade preserves data and dependencies, so
batch upgrade inherits that and does not gate.

If a plugin's dependencies require a co-upgrade that SN refuses,
the per-plugin `submit_upgrade` will surface the error and the
batch will record it as `failed` with that reason -- no special
handling needed.

### Concurrency

Sequential. Each upgrade kicks a tracker; SN's progress system
isn't designed for many concurrent app-manager trackers per
instance, and Rich progress rendering stays clean with one active
op at a time. Adding bounded concurrency later is a one-line
`asyncio.Semaphore` addition if real-world batches prove too slow.
Out of scope for v1.

### What entry point?

Extend `nexus plugins updates` with three new flags:

- `--apply` -- destructive; without it the command remains the
  current dry-run listing
- `--family NAME` (repeatable) -- filter to one or more families
- `--out PATH` -- write a `BatchUpgradeReport` YAML

Reasons:
- The command already lists what would be upgraded, so the user
  sees the candidate set immediately before opting in with `--apply`.
- One concept, one command. No new top-level surface.
- `--queue` (existing) and `--out` (new) coexist: `--queue` is the
  pre-flight YAML (input to `apply`), `--out` is the post-run YAML
  (result of the batch).

## Architecture

```
nexus plugins updates [--family X]* [--apply] [--out file] [--yes]
        |
        | filter by family (in-memory, on product_family)
        v
   filtered: tuple[PluginInfo, ...]   (plugins_with_updates result)
        |
        +-- no --apply --> print table, exit 0
        |
        +-- --apply --> PluginExecutor.batch_upgrade(targets, console=...)
                          |
                          | for plugin in targets:
                          |     result = await self.upgrade(plugin_id, target_version)
                          |     append to results
                          |     update live table row
                          v
                       BatchUpgradeReport (frozen, Pydantic)
                          |
                          +-- print summary panel
                          +-- write --out PATH (if set)
                          +-- exit 0 if all succeeded, 1 otherwise
```

## Models

New frozen Pydantic model in `src/nexus/plugins/executor.py`:

```python
class BatchUpgradeReport(BaseModel):
    """Aggregate result of PluginExecutor.batch_upgrade.

    Attributes:
        results: One OperationResult per attempted plugin, in
            execution order. Reuses the existing model verbatim.
        families: The families filter that produced the target set,
            empty tuple when no filter was applied.
        target_count: Number of plugins attempted (==len(results)).
        succeeded: Number of results with success=True.
        failed: Number of results with success=False.
    """

    model_config = _FROZEN

    results: tuple[OperationResult, ...]
    families: tuple[str, ...]
    target_count: int
    succeeded: int
    failed: int

    @property
    def exit_code(self) -> int:
        """0 when all succeeded (including empty target -- idempotent), 1 when any failed."""
        return 0 if self.failed == 0 else 1
```

An empty target set (after family filter, nothing pending) is
idempotent success, not an error. The CLI logs "nothing to upgrade"
and exits 0. Exit code 2 is reserved for genuine user errors
(unknown family name).

Re-export from `src/nexus/plugins/__init__.py`.

## PluginExecutor.batch_upgrade

New method on `PluginExecutor`:

```python
async def batch_upgrade(
    self,
    targets: tuple[PluginInfo, ...],
    *,
    families: tuple[str, ...] = (),
    console: Console,
) -> BatchUpgradeReport:
    """Upgrade each plugin in order, skip-on-fail.

    Targets are filtered upstream (by family, by needs-update); this
    method just executes them. Each plugin is upgraded to
    plugin.latest_version (None means "latest" -- delegated to
    submit_upgrade).

    Failures are recorded but never abort the batch. No rollback.

    Args:
        targets: Plugins to upgrade, in the order they should run.
        families: Family names used to filter targets, echoed back
            on the report. Empty tuple for un-filtered batches.
        console: Rich console for live progress updates.

    Returns:
        BatchUpgradeReport with per-plugin OperationResult.
    """
```

Implementation: a `for` loop calling `self.upgrade(plugin_id,
plugin.latest_version)` and appending results. Console output uses
a Rich Live table that updates the row status (running -> ok / fail)
as each plugin completes. No new HTTP plumbing.

## Filter helpers

New module `src/nexus/plugins/filters.py`:

```python
__all__ = ["filter_by_family", "available_families"]

def filter_by_family(
    plugins: tuple[PluginInfo, ...],
    families: tuple[str, ...],
) -> tuple[PluginInfo, ...]:
    """Return plugins matching any of the given families (case-insensitive)."""

def available_families(
    plugins: tuple[PluginInfo, ...],
) -> tuple[tuple[str, int], ...]:
    """Return (family, count) pairs sorted by family name."""
```

Pure functions. No SN calls. ~30 LOC including docstrings.

## CLI changes

Modify `plugins_updates` at `src/nexus/cli.py:2389`:

- Add `--family NAME` (repeatable, list[str]) -- matches the
  existing command's long-flags-only convention
- Add `--apply` (bool flag, default False)
- Add `--out PATH` (optional Path)
- Add `--yes / -y` (bool flag, skip the confirmation prompt)
- Keep `--queue PATH` and JSON output unchanged

Flow:

1. Build inventory via `_load_inventory_or_exit`.
2. `pending = plugins_with_updates(inventory)`.
3. If `--family` provided:
   - Validate each name against `ProductFamily` enum (case-insensitive).
   - On unknown: print available families table from
     `available_families(inventory.plugins)`, exit code 2.
   - Filter `pending` via `filter_by_family`.
4. Render the candidate table (existing format).
5. If not `--apply`: exit 0 (existing dry-run behaviour).
6. If `--apply`:
   - If not `--yes`: prompt for confirmation (type `yes`).
   - Build `PluginExecutor` from inventory + client.
   - Call `executor.batch_upgrade(pending, families=tuple(family_args), console=console)`.
   - Render summary panel (`N upgraded, M failed`).
   - If `--out`: write `BatchUpgradeReport` as YAML to PATH.
   - `raise typer.Exit(report.exit_code)`.

## Error handling

- Unknown family name -> exit 2 + family list output.
- Empty target set after filter (when `--apply` is given) ->
  print "no plugins need updates" message, exit 0 (idempotent
  success).
- Per-plugin failures -> recorded in report, batch continues, exit 1.
- Confirmation declined -> exit 130 (standard "user cancelled").

## Test plan

**Unit tests** (no SN calls; FakeServiceNowClient + fakes):

`tests/plugins/test_filters.py` (new):
- `test_filter_by_family_single_match` -- one family, two plugins
- `test_filter_by_family_multiple_families` -- ITSM + ITOM union
- `test_filter_by_family_case_insensitive` -- "itsm" matches "ITSM"
- `test_filter_by_family_empty_filter` -- returns all
- `test_filter_by_family_no_match` -- returns empty tuple
- `test_available_families_counts` -- sorted with counts

`tests/plugins/test_batch_upgrade.py` (new):
- `test_batch_upgrade_all_succeed` -- 3 plugins, all OK
- `test_batch_upgrade_one_fails_others_continue` -- middle plugin
  fails; the third still runs and succeeds
- `test_batch_upgrade_records_families` -- echo input families
  on report
- `test_batch_upgrade_empty_targets` -- target_count=0, exit_code=2
- `test_batch_upgrade_report_exit_code` -- 0 / 1 / 2 paths
- `test_batch_upgrade_no_rollback_on_failure` -- assert
  `_rollback` is NOT called (use a fake executor subclass that
  raises if `_rollback` runs)

`tests/cli/test_plugins_updates_apply.py` (new):
- `test_plugins_updates_apply_dry_run` -- no `--apply` flag, only
  lists pending
- `test_plugins_updates_apply_executes` -- `--apply --yes` calls
  batch_upgrade once
- `test_plugins_updates_family_filter` -- `-f ITSM` shrinks the set
- `test_plugins_updates_unknown_family_exits_2` -- exit code 2 +
  available families printed
- `test_plugins_updates_writes_out_yaml` -- `--out report.yaml`
  contains expected keys
- `test_plugins_updates_confirms_without_yes` -- prompt runs when
  `--yes` is absent

**Smoke tests** (`scripts/smoke_plugins.py`, additions):
- `smoke_plugins_updates_family_filter` -- live `--family Platform`
  produces a sensible non-empty set
- `smoke_plugins_updates_unknown_family` -- exit code 2 +
  available families listed
- `smoke_plugins_updates_dry_run` -- `--apply` not passed: no
  side effects

(No live `--apply` smoke -- alectri PDI is not a throwaway and
real upgrades on it are out-of-band. Existing single-upgrade smoke
in the suite already covers the live path.)

Target test delta: ~16 new tests, all green. Coverage on
`executor.py` and `filters.py` should hit ratchet baseline.

## File plan

Create:
- `src/nexus/plugins/filters.py` (~50 LOC with headers + docstrings)
- `tests/plugins/test_filters.py` (~60 LOC)
- `tests/plugins/test_batch_upgrade.py` (~140 LOC)
- `tests/cli/test_plugins_updates_apply.py` (~180 LOC)

Modify:
- `src/nexus/plugins/executor.py` -- add `BatchUpgradeReport` model
  and `batch_upgrade` method (~80 LOC of code + docstrings)
- `src/nexus/plugins/__init__.py` -- re-export `BatchUpgradeReport`
  and the two filter helpers
- `src/nexus/cli.py` -- extend `plugins_updates` command
  (~70 LOC of new flags + flow)
- `scripts/smoke_plugins.py` -- 3 new smoke tests

Not touched:
- `scanner.py`, `models.py`, `product_families.py` -- already supply
  what we need
- `progress.py`, `dependencies.py` -- per-plugin path reused as-is
- `apply_plan` -- unchanged, different audience
- `connectors/servicenow/client.py` -- no new SN endpoints

## Estimate

- New code: ~520 LOC across 4 new + 4 modified files
- Tests: ~16 new
- Effort: 4-6 hours implementation + review (single-day deliverable)
- Risk: low. Reuses primitives. No new SN endpoints. No new auth.
  Smoke covers the integration paths.

## Open questions

None for v1. Concurrency, a separate `families` subcommand, and
batch deactivate/uninstall are intentionally deferred.

## Related

- Parent: docs/superpowers/specs/2026-05-13-plugin-execution-design.md
  (sub-projects M + N, addenda 2026-05-14a..e)
- Roadmap: .primer/roadmap.md (Plugin Execution section, this is a
  small follow-on enhancement to the shipped scope)
