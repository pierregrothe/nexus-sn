# Story 01: TemplateEntry + TemplateManifest + CachedManifest models

Status: done
Spec-Clarity: high
Depends-On: none

## Story

As `nexus sync` and `nexus templates`,
I want typed Pydantic models for the wire payload and the on-disk
cache,
so that a single `extra="forbid"` configuration cannot break round-trip
serialization between what GitHub serves and what we store locally.

## Acceptance Criteria

AC1:
**Given** the seed manifest `{"version": "1.0", "generated":
"2026-05-07", "templates": []}`
**When** parsed by `TemplateManifest.model_validate_json(payload)`
**Then** it returns a frozen `TemplateManifest` with `version="1.0"`,
`generated="2026-05-07"`, `templates=()`.

AC2:
**Given** a manifest with one entry
`{"name": "incident-ai-agent", "template_type": "ai_agent",
"version": "0.1.0", "path": "ai_agents/incident.yaml"}`
**When** parsed
**Then** `TemplateEntry` accepts it; `checksum` defaults to `None`.

AC3:
**Given** a wire payload that includes a `cached_at` key
**When** `TemplateManifest.model_validate_json` runs
**Then** it raises `ValidationError` (extra="forbid" rejects it).
The wire model has no `cached_at` field.

AC4:
**Given** a `TemplateManifest` + a `SyncSource(repo, branch, path)`
+ `datetime.now(UTC)`
**When** wrapped as `CachedManifest(wire=..., cached_at=..., source=...)`
**Then** `CachedManifest.model_dump_json()` round-trips back through
`CachedManifest.model_validate_json(...)` without error.

AC5:
**Given** any Pydantic model in this story
**When** introspected
**Then** `model_config` is
`ConfigDict(frozen=True, strict=True, extra="forbid")`.

## Must NOT

- Must NOT use Python's `type` builtin name as a field. Use
  `template_type`.
- Must NOT introduce `Optional[X]` from `typing`. Use `X | None`.
- Must NOT make `cached_at` a regular `datetime`. Use `UtcDatetime`
  from `nexus.config.types`.
- Must NOT subclass between wire and cached models. They are
  separate composition; `CachedManifest` HAS a `TemplateManifest`.

## Tasks / Subtasks

- [ ] Create `src/nexus/templates/models.py` (AC: 1-5)
  - [ ] File header, Google docstrings, `__all__`
  - [ ] Module-level `_FROZEN = ConfigDict(frozen=True, strict=True, extra="forbid")`
  - [ ] `TemplateEntry(BaseModel)` -- name, template_type, version,
        path, checksum
  - [ ] `TemplateManifest(BaseModel)` -- version, generated, templates
        (`tuple[TemplateEntry, ...]`)
  - [ ] `SyncSource(BaseModel)` -- repo, branch, path
  - [ ] `CachedManifest(BaseModel)` -- wire (TemplateManifest),
        cached_at (UtcDatetime), source (SyncSource)
- [ ] Create `tests/test_templates_models.py` (AC: 1-5)
  - [ ] `test_template_manifest_parses_seed_payload`
  - [ ] `test_template_entry_accepts_required_fields_and_optional_checksum`
  - [ ] `test_template_manifest_rejects_extra_fields`
  - [ ] `test_cached_manifest_round_trips_json`
  - [ ] `test_template_manifest_template_type_field_replaces_type_keyword`
  - [ ] `test_cached_manifest_requires_utc_aware_datetime`
  - [ ] `test_template_manifest_accepts_empty_templates_array`

## Existing Code

Greenfield. The stub at `src/nexus/templates/__init__.py` exports
nothing; we will add re-exports of the four models.

## Dev Notes

### Modules Affected

- `src/nexus/templates/models.py` (new)
- `src/nexus/templates/__init__.py` (re-export the new models)
- `tests/test_templates_models.py` (new)

### Testing Approach

- Function-based pytest tests (project convention).
- Parametrize valid / invalid round-trips.
- Naming: `test_<function>_<scenario>`.

### Conventions

- See `~/.claude/rules/pydantic-conventions.md`, file-headers,
  module-exports.

## References

- Brainstorming: `.primer/brainstorming/2026-05-18-nexus-sync-catalog.md`
  Recommendation 1, AC table
- Precedent: `src/nexus/instances/models.py:33-90`
