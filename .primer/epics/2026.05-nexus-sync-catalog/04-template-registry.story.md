# Story 04: TemplateRegistry (atomic save_manifest + load_manifest)

Status: backlog
Spec-Clarity: high
Depends-On: 01

## Story

As `nexus sync` and `nexus templates`,
I want a typed registry that owns the local manifest cache with
atomic writes,
so that an interrupted sync never leaves a partial / unreadable
manifest on disk and the next `nexus templates` invocation either
sees the previous valid cache or learns that no cache exists.

## Acceptance Criteria

AC1:
**Given** a fresh `tmp_path` and `TemplateRegistry(tmp_path)`
**When** `load_manifest()` is called
**Then** it returns `None` (no cache).

AC2:
**Given** a `TemplateManifest` `M` and a `SyncSource` `S`
**When** `registry.save_manifest(M, S)` is called
**Then** it writes `<tmp_path>/manifest.json`, returns a
`CachedManifest` whose `wire == M`, `source == S`, and `cached_at`
is `datetime.now(UTC)` (within a 1-second window).

AC3:
**Given** a manifest was saved
**When** `load_manifest()` is called
**Then** it returns the same `CachedManifest` (wire + source +
cached_at all equal modulo serialization).

AC4:
**Given** a corrupted `manifest.json` on disk (invalid JSON)
**When** `load_manifest()` is called
**Then** it returns `None` and logs a `warning`. The corrupted file
is NOT touched (so the user can inspect).

AC5:
**Given** a stale-schema `manifest.json` (valid JSON but fails
`CachedManifest.model_validate_json`)
**When** `load_manifest()` is called
**Then** it returns `None` and logs a `warning` containing the loc
of the first error.

AC6:
**Given** the parent directory does not exist
**When** `save_manifest(M, S)` is called
**Then** it creates the directory tree with `parents=True,
exist_ok=True` and writes the file successfully.

AC7:
**Given** a write fails (e.g., simulated `OSError`)
**When** `save_manifest(M, S)` raises
**Then** the previous cache (if any) is unchanged, and any tempfile
is cleaned up.

## Must NOT

- Must NOT swallow `OSError` from `save_manifest`. The orchestrator
  needs to know writes failed so it can surface the reason.
- Must NOT log the manifest contents (could be large; could
  eventually contain user-specific data).
- Must NOT use `naive datetime`. `cached_at` is `datetime.now(UTC)`.
- Must NOT use `json.dump` with file path; use
  `tempfile.mkstemp(dir=target.parent)` + `Path(tmp).replace(target)`
  pattern from `InstanceRegistry._atomic_write_to`.

## Tasks / Subtasks

- [ ] Create `src/nexus/templates/registry.py`
  - [ ] File header + docstrings + `__all__`
  - [ ] `class TemplateRegistry:` with `__init__(self,
        templates_dir: Path)`
  - [ ] `_MANIFEST_FILE = "manifest.json"` module constant
  - [ ] `save_manifest(manifest, source) -> CachedManifest`:
        wraps in `CachedManifest` with `cached_at = datetime.now(UTC)`;
        atomic write via mkstemp + replace; returns the wrapper
  - [ ] `load_manifest() -> CachedManifest | None`: read file; if
        missing return None; if JSONDecodeError -> log warning,
        return None; if ValidationError -> log warning, return None
- [ ] Tests in `tests/test_templates_registry.py`
  - [ ] `test_load_manifest_returns_none_when_cache_missing`
  - [ ] `test_save_manifest_writes_file_and_returns_cached_wrapper`
  - [ ] `test_save_manifest_stamps_cached_at_in_utc`
  - [ ] `test_save_then_load_round_trips_manifest`
  - [ ] `test_load_manifest_returns_none_on_malformed_json`
  - [ ] `test_load_manifest_returns_none_on_schema_mismatch`
  - [ ] `test_save_manifest_creates_parent_directories`
  - [ ] `test_save_manifest_preserves_previous_cache_when_write_fails`

## Existing Code

- Mirror the atomic-write idiom from
  `src/nexus/instances/registry.py:_atomic_write_to`.
- Use `Path.read_text(encoding="utf-8")` for the load.

## Dev Notes

### Modules Affected

- `src/nexus/templates/registry.py` (new)
- `src/nexus/templates/__init__.py` (re-export `TemplateRegistry`)
- `tests/test_templates_registry.py` (new)

### Testing Approach

- `tmp_path` for real disk operations.
- Use a subclass / closure trick to inject an `OSError` for AC7
  (e.g., monkeypatch `pathlib.Path.replace` -- without using
  `unittest.mock`, just `monkeypatch.setattr`).
- Function-based naming.

### Conventions

- See `~/.claude/rules/utc-timezone.md` for `cached_at`.

## References

- Brainstorming: Recommendation 2, Failure-mode-rows 4 + 5
- Precedent: `src/nexus/instances/registry.py`
