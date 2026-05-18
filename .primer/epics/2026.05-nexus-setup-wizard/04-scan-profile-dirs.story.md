# Story 04: InstanceRegistry.scan_profile_dirs() exposes corrupted entries

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As `nexus setup`'s idempotent gate,
I want a registry API that returns BOTH valid profiles and corrupted
profile entries (the ones `list_all()` silently drops at
`registry.py:119-120`),
so that a malformed `meta.json` surfaces an error with the offending
path instead of being mistaken for "no instance configured."

## Acceptance Criteria

AC1:
**Given** `~/.nexus/instances/` contains directories `prod/`, `dev/`,
and `broken/`, where `prod/meta.json` and `dev/meta.json` parse cleanly
but `broken/meta.json` has invalid JSON
**When** `registry.scan_profile_dirs()` is called
**Then** it returns a `ScanResult` (frozen dataclass) with
`valid: list[InstanceMeta]` of length 2 (prod, dev) and
`corrupted: list[CorruptedProfile]` of length 1 (broken), where each
`CorruptedProfile` carries `path: Path` and `reason: str`.

AC2:
**Given** `~/.nexus/instances/` does not exist
**When** `scan_profile_dirs()` is called
**Then** it returns `ScanResult(valid=[], corrupted=[])` -- no
exception.

AC3:
**Given** a profile dir exists but contains no `meta.json` (e.g., an
empty directory or one with unrelated files)
**When** `scan_profile_dirs()` is called
**Then** that directory contributes a `CorruptedProfile` with
`reason="missing meta.json"`.

AC4:
**Given** a profile dir contains a `meta.json` that parses as JSON but
fails Pydantic validation (e.g., missing `host` field)
**When** `scan_profile_dirs()` is called
**Then** that directory contributes a `CorruptedProfile` with
`reason` summarizing the Pydantic error in one line.

AC5: `list_all()` behavior is UNCHANGED. Existing callers continue to
see the silent-skip semantics.

## Must NOT

- Must NOT modify `list_all()`'s contract -- callers in `cli/` rely on
  it. Add the new method side-by-side.
- Must NOT raise from `scan_profile_dirs()` on any per-profile error;
  collect into `corrupted` instead.
- Must NOT use `dict[str, Any]` in any new Pydantic model field.
- Must NOT log secrets if `meta.json` contained any (it should not, but
  the reason string must never include the file contents -- only the
  exception class name + field name).

## Tasks / Subtasks

- [ ] Add `CorruptedProfile` frozen dataclass to
      `src/nexus/instances/registry.py` (AC: 1)
  - [ ] Fields: `path: Path`, `reason: str`
  - [ ] `slots=True`
- [ ] Add `ScanResult` frozen dataclass (AC: 1)
  - [ ] Fields: `valid: tuple[InstanceMeta, ...]`, `corrupted: tuple[CorruptedProfile, ...]`
  - [ ] Use `tuple` for immutability (matches frozen convention)
- [ ] Implement `scan_profile_dirs(self) -> ScanResult` (AC: 1, 2, 3, 4)
  - [ ] Iterate `self.instances_dir.iterdir()` if it exists, else empty
  - [ ] For each subdir: read `meta.json`, parse JSON, validate via
        `InstanceMeta.model_validate_json`
  - [ ] On `json.JSONDecodeError` / `ValidationError` / `OSError`,
        append `CorruptedProfile` with a one-line reason
  - [ ] Sort `valid` by profile name for deterministic output
- [ ] Update `__all__` in `registry.py`
- [ ] Add tests in `tests/test_instances_registry.py` (AC: 1-5)
  - [ ] `TestScanProfileDirs`: fixture builds a tmp `instances_dir`
        with one valid + one invalid-json + one missing-meta dir
  - [ ] One test per AC row
  - [ ] One test that calls `list_all()` against the same tmp dir and
        confirms it still returns only the valid profile (AC5)

## Existing Code

- `src/nexus/instances/registry.py:48-57` -- `register()`, unchanged
- `src/nexus/instances/registry.py:105-121` -- `list_all()`, unchanged
- `src/nexus/instances/models.py:33-90` -- `InstanceMeta`, used as-is

## Dev Notes

### Modules Affected

- `src/nexus/instances/registry.py`
- `tests/test_instances_registry.py`

### Testing Approach

- Class-based pytest tests (`TestScanProfileDirs`). `tmp_path` fixture
  builds real directory structures with real (in)valid meta.json files.
  No fakes for the filesystem -- pytest's tmp_path is the real thing.
- Each invalid case is constructed via `(tmp_path / "broken" /
  "meta.json").write_text(...)`.
- Assert on `ScanResult` field values directly; do not introspect
  internals.

### Conventions

- Frozen dataclass + `slots=True` for `ScanResult` and `CorruptedProfile`.
- `pathlib.Path`, never `os.path`.
- Python 3.14 union syntax in type hints.

## References

- Brainstorming: `.primer/brainstorming/2026-05-18-nexus-setup-credential-wizard.md`,
  section "Failure-mode handling" row 2 + adversarial review item 3
- Existing: `src/nexus/instances/registry.py:105-121`
