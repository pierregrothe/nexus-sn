# Story 01: full-fidelity selective capture

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a NEXUS developer building the migration planner's closure computation,
I want ConfigFetcher to preserve bool/int/float/None field values and a
selection-to-capture translation that turns a checklist selection into full
CaptureResults for exactly the selected scopes/tables,
so that closure can walk real reference-field VALUES instead of the
name-only checklist listing.

Two deltas as one vertical slice: (a) capture-layer scalar fidelity, (b)
selection-to-capture translation.

## Acceptance Criteria

AC1 (SnFieldValue widened):
**Given** `SnFieldValue` in `src/nexus/capture/models.py`
**When** redefined
**Then** it is `type SnFieldValue = str | bool | int | float | None |
SnRefField` (the existing string and reference-dict shapes plus the three
JSON scalar kinds and null).

AC2 (`_row_to_record` preserves scalars):
**Given** `_row_to_record` in `src/nexus/capture/fetcher.py`
**When** a row contains bool/int/float/None field values alongside string
and reference-dict fields
**Then** every field survives into `ConfigRecord.fields` with its native
Python type -- no field is silently dropped.

AC3 (archive round-trip):
**Given** a `ConfigRecord` with bool/int/float/None field values
**When** written via the existing archive writer and read back via the
archive reader
**Then** every field value round-trips type-for-type identical (emit ->
load -> compare).

AC4 (selection-to-capture translation, happy path, GWT):
**Given** a `Selection` (Story 02) naming a subset of scopes+tables
**When** `build_capture_for_selection(client, selection, table_groups)` in
`src/nexus/migrate/capture_bridge.py` runs
**Then** it issues `ConfigFetcher.fetch()` queries scoped to exactly those
scope sys_ids and tables, and returns `CaptureResult` tuple(s) containing
only the selected artifacts' full records (not a name-only listing).

AC5 (partial selection, no over-fetch):
**Given** a `Selection` naming only some tables within a table group
**When** the translation runs
**Then** it does not fetch tables outside the named subset.

AC6 (empty selection, GWT):
**Given** an empty `Selection`
**When** the translation runs
**Then** it returns an empty `CaptureResult` tuple without issuing any
`ConfigFetcher` call.

## Must NOT

- Must NOT change natural-key normalization (`key =
  f"{scope}|{type}|{casefold(collapse_ws(name))}"` stays exactly as shipped
  in `replatform/`).
- Must NOT make any live-instance call from tests -- all fetcher/translation
  tests run against a capture-layer fake, never a real `ServiceNowClient`.
- Must NOT touch `src/nexus/replatform/` classification or diff logic --
  this story is capture-layer + a new `migrate/` bridge module only.

## Tasks / Subtasks

- [ ] Widen `SnFieldValue` type alias in `src/nexus/capture/models.py` (AC1)
- [ ] Update `_row_to_record` in `src/nexus/capture/fetcher.py` to keep
      bool/int/float/None fields (AC2)
- [ ] Extend the capture-layer fake with rows carrying scalar field types
      (AC2, AC3)
- [ ] Extend archive round-trip tests for scalar fidelity (AC3)
- [ ] Create `src/nexus/migrate/__init__.py` + `src/nexus/migrate/capture_bridge.py`
      -- `build_capture_for_selection` (AC4-AC6)
- [ ] Create `tests/test_capture_fetcher_scalars.py` and
      `tests/test_migrate_capture_bridge.py` (AC1-AC6)

## Existing Code

- `src/nexus/capture/fetcher.py` -- `_row_to_record`, `ConfigFetcher.fetch`
  (the function being fixed).
- `src/nexus/capture/models.py` -- `SnFieldValue`, `SnRefField`,
  `ConfigRecord`.
- `src/nexus/capture/archive.py` -- writer/reader the round-trip test
  exercises.
- `src/nexus/capture/tables.py` -- `TableGroup`/`TableSpec` used to scope
  the translation's fetch plan.

## Dev Notes

### Modules Affected

- `src/nexus/capture/models.py`, `src/nexus/capture/fetcher.py` (delta a)
- `src/nexus/migrate/__init__.py`, `src/nexus/migrate/capture_bridge.py`
  (delta b, first `migrate/` module -- per ADR-026#Decision 1 it imports
  only from `capture/`, `plugins/`, `instances/`, `config/`, never `cli/`
  or `agents/`)
- `tests/fakes/fake_sn_client.py` (scalar-bearing fixture rows)
- `tests/test_capture_fetcher_scalars.py`, `tests/test_migrate_capture_bridge.py`

### Testing Approach

- Function-based pytest, `test_<func>_<scenario>` naming (e.g.
  `test_row_to_record_preserves_bool_field`,
  `test_build_capture_for_selection_empty_selection`).
- No mocks; capture-layer tests use the existing fake ServiceNow client in
  `tests/fakes/`; add scalar-typed rows to its canned data rather than
  introducing a new mock.
- Archive round-trip asserted as emit -> load -> compare on the in-memory
  model, mirroring the existing archive test pattern.

## References

- PRD: `.primer/prd/PRD-005-nexus-migration-planner.md#In Scope`
  ("Prerequisite fixes"), `#Acceptance Criteria` (round-trip bullet)
- ADR: `.primer/adr/ADR-026-selective-migration-planner.md#Decision 1`
  (package boundary), `#Decision 7` (capture prerequisites)
- Brainstorming:
  `.primer/brainstorming/2026-07-02-selective-migration-planner.md#Recommendation 6`
  (milestone-1 prerequisites), `#Research Findings Appendix` (Repo
  primitives inventory -- "Known fidelity bug")
