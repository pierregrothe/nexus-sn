# Story 00: S0 closure-scale spike -- results

Measured 2026-07-02 (UTC). Read-only; nothing was written to any ServiceNow
instance. All numbers below come from a real run of
`scripts/spike_s0_closure_scale.py` over the already-captured 30K-artifact
inventory JSONs plus a live-fetched offline schema-graph archive.

## AC2 measurement table

| Measurement | Value |
|---|---|
| Closure wall-clock at 30K artifacts | **10.75ms** (alectri, 30,463 artifacts, seed-stop-list walk; JSON load for both inventories + the schema archive is a separate 0.200s, not counted in the headline) |
| Finding count without stop-list | raw candidates **40,306** / deduped findings **351** |
| Finding count with seed stop-list | raw candidates **40,306** (expansion 40,306 / data-prerequisite 0) / deduped findings **351** (expansion 351 / data-prerequisite 0) |
| Lane-unit count | **95** = 82 scoped apps + 13 global use cases + 0 data batches |

Retail (30,398 artifacts) was walked as a confirmation run with the same
schema graph and stop-list: raw 40,309 / deduped 348 in 11.22ms -- consistent
with alectri, confirming the harness generalizes across the two captured
instances (AC1 requires both be loaded as fixed input; alectri is the
headline instance because it is the one that is ~30K artifacts, matching the
story's "30K-artifact dataset" framing).

## Important caveat: the seed stop-list produced zero dampening here

The empty-stop-list and seed-stop-list rows are numerically identical
(40,306 raw / 351 deduped either way). This is not a bug in the walk --
`scripts/spike_s0_closure_scale.py`'s stop-list dampening is unit-tested and
demonstrated working against a fixture (`tests/spikes/test_spike_s0_closure_scale.py::test_walk_closure_seed_stop_list_dampens_matching_edges`).
It is a real, measured fact about the 9 artifact tables' *schema-declared*
reference fields: the live fetch against alectri found only 8
`sys_dictionary` rows with `internal_type=reference` (or `glide_list`)
across all 9 tables combined, and none of the 8 target `sys_user`,
`sys_user_group`, `sys_choice`, or `cmdb_ci`. See "Schema-graph fetch"
below for the full edge list. Most of a Business Rule's or Flow's real
dependencies (an `assigned_to` value inside a script body, a group
referenced by a Flow Designer input) live in script/flow *content*, not in
a dictionary-declared reference column on the table itself -- and
script-body/flow-input scanning is explicit v1 out-of-scope per
`ADR-026` Decision 7 and the epic's Out-of-Scope list. This spike's
structural, table-level closure is therefore a real but narrow slice of
the full dependency picture; the "hundreds, not tens of thousands" finding
count the PRD hoped for (`PRD-005#Success Metrics`) is true here, but for a
different reason than stop-list dampening -- the schema-declared edge set
for these 9 tables is inherently sparse.

## Closure-walk semantics (structural upper bound)

The inventories are name-only (artifact name/type/scope; no field *values*),
so per-artifact reference values are unknown. For every artifact, every
reference edge declared on its table is counted as a raw closure
*candidate* -- not a confirmed dependency. This is a structural upper
bound, not an exact count: a `sys_script` row's `sys_overrides` field being
declared as a reference to `sys_script` does not mean every one of the
8,281 `sys_script` artifacts actually populates that field. Findings are
deduplicated at `(use_case, from_table, field, to_table)` granularity for
the "deduped" numbers.

## Schema-graph fetch

`scripts/spike_s0_fetch_schema_edges.py` ran once against profile `alectri`
(2026-07-02T13:00:37Z), querying `sys_dictionary` for the 9 artifact tables
restricted to `elementISNOTEMPTY^referenceISNOTEMPTY`
(read-only Table API GET; no `SchemaDiscoverer`/full-scope reverse
engineering, which would have pulled the entire `global`-scope platform
dictionary). Result: 8 reference edges across 5 source tables, 12 tables
total in the archive (9 artifact tables + 3 reference targets:
`sys_rest_message`, `sys_rest_message_fn`, `sys_ui_view`).

| from_table | field | to_table |
|---|---|---|
| sys_script | rest_method | sys_rest_message_fn |
| sys_script | rest_service | sys_rest_message |
| sys_script | sys_overrides | sys_script |
| sys_script_client | sys_overrides | sys_script_client |
| sys_ui_action | sys_overrides | sys_ui_action |
| sys_ui_policy | sys_overrides | sys_ui_policy |
| sys_ui_policy | view | sys_ui_view |
| wf_workflow | sys_overrides | wf_workflow |

`sys_script_include`, `sysauto_script`, `sys_hub_flow`, and
`sys_hub_action_type_definition` have zero dictionary-declared reference
fields. The archive JSON is untracked (see Gitignore below); regenerate it
with the command in the next section.

## Seed stop-list

`.primer/epics/2026.08-nexus-migration-planner/seed-stop-list.yaml` holds
the mandatory baseline from the story brief: `sys_user`, `sys_user_group`,
`sys_choice`, `cmdb_ci`. No additional "kin" were added -- none of the 8
observed reference targets above are instance-data tables (they are all
config: REST message definitions, a UI view, or self-references), so there
was nothing in the fetched edge set to extend the list with.

## Lane-unit count breakdown

| Addend | Value | Definition |
|---|---|---|
| Scoped apps (APP_REPO-lane candidates) | 82 | Distinct `x_`/`u_` custom scope keys in the alectri inventory |
| Global use cases (UPDATE_SET-sized groupings) | 13 | Distinct use-case keys with at least one `global`-scope workflow |
| Data batches (DATA-lane buckets) | 0 | Distinct stop-list tables hit by >=1 dampened edge (none, per the caveat above) |
| **Total** | **95** | |

Cross-check: alectri's 95 use cases split cleanly into 82 whose workflows
are entirely in a custom scope and 13 whose workflows are entirely
`global`-scope, with zero use cases mixing both -- the scoped-app and
global-use-case addends are a clean partition of the inventory's use cases,
not an overlapping or approximate count.

## Regenerating every input

The two inventory JSONs (untracked, regenerable, from
`artifacts/replatform-proof/verification-summary.md` "Regenerating the
large artifacts", run from `artifacts/replatform-proof/`):

```
nexus assess inventory alectri --out inventory-alectri-v2.json
nexus assess inventory retail  --out inventory-retail-v2.json
```

The schema-graph archive (untracked, regenerable; read-only; profile
restricted to `alectri`/`retail`):

```
poetry run python scripts/spike_s0_fetch_schema_edges.py --profile alectri
```

The measurement run itself (not a pytest test -- CI must not depend on the
untracked 6MB inventories; this is the human-run command whose output fed
the numbers above). Redirect to a file rather than piping through a pager --
piping the harness's stdout into `head`/`more` can SIGPIPE the process
before output flushes:

```
poetry run python scripts/spike_s0_closure_scale.py > s0-run.txt
```

## Design decisions made while executing this story

- **Inventory and schema-archive parsing is plain `json.loads`, not
  `nexus.replatform.models.UseCaseInventory` /
  `nexus.schema.archive.SchemaArchiveReader`.** Importing any
  `nexus.schema` submodule (even `nexus.schema.models` alone) executes
  `nexus/schema/__init__.py`, which eagerly imports `nexus.schema.engine`
  and, transitively, `httpx`/`nexus.connectors`/`nexus.api` -- verified by
  import-graph inspection before writing the harness. AC5 requires the
  harness to construct zero network clients; rather than depend on that
  import graph and rely solely on runtime behavior to avoid touching it,
  the harness never imports any `nexus.*` module at all, so the AC5 guard
  (`_assert_no_network_client`) is trivially and structurally satisfiable.
- **`scripts/` is already a package** (`pythonpath = ["src", "scripts"]` in
  `pyproject.toml` plus `scripts/__init__.py`), and
  `tests/test_check_file_sizes.py` already imports
  `from scripts.check_file_sizes import _check, _load_baseline` -- contrary
  to the story brief's assumption that "scripts/ is not a package" /
  "nothing imports from scripts/ today". The test file follows that
  existing precedent (`from scripts.spike_s0_closure_scale import ...`)
  instead of using `importlib.util.spec_from_file_location`, which would
  have been more complex for no benefit.
- **`_assert_no_network_client` takes an injectable `modules` mapping**
  (default `sys.modules`) rather than reading `sys.modules` unconditionally.
  `tests/conftest.py` imports `httpx` at module scope for unrelated fixture
  needs, so `httpx` is always present in `sys.modules` inside the pytest
  process -- calling the guard with no argument inside a test would always
  (correctly, but unhelpfully) fail. Injecting the mapping lets tests
  exercise both the pass and fail branches deterministically; `main()`
  calls it with no argument, so the real guard still checks the live
  `sys.modules`.
- **Two separate scripts, per the story brief**: `spike_s0_fetch_schema_edges.py`
  (live, one-time, read-only) and `spike_s0_closure_scale.py` (pure, no
  network). Neither lives under `src/nexus/` (Must-NOT).

## Gitignore

`artifacts/replatform-proof/inventory-*-v2.json` was already ignored.
Extended with `artifacts/replatform-proof/*/s0-platform-artifacts-*.json` to
also cover the fetched schema-graph archive
(`artifacts/replatform-proof/alectri/s0-platform-artifacts-*.json`) without
touching the already-tracked files that live directly under
`artifacts/replatform-proof/` (`verification-summary.md`,
`replatform-checklist*.md`, etc. -- confirmed via `git ls-files`).
