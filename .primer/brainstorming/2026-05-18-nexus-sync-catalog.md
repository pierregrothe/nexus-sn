# Brainstorming: nexus sync v1 (catalog index)

Date: 2026-05-18
Mode: assumptions (research-driven, skipped technique rounds)
Techniques: assumptions-mode + adversarial-review
Trigger: `nexus sync` is a `NotImplementedError` stub at
`src/nexus/cli/commands_top.py:139`. The roadmap's `2026.05-setup-sync`
phase needs sync to ship now that the setup wizard is done (commits
1eca36f + fd0f0df).

## Context Brief

NEXUS is a Python 3.14 CLI for ServiceNow architect work. The
sync feature pulls a template catalog manifest from a GitHub repo
and caches it locally under `~/.nexus/templates/`. Per-template YAML
downloads, schema validation, and the `apply` engine are explicit
non-goals for v1 (those live in `2026.06-template-library`).

Existing scaffolding:

- `src/nexus/templates/sync.py` and `registry.py` are 2-line stubs.
- `src/nexus/templates/__init__.py` is a 2-line stub.
- Empty schema stubs under `src/nexus/templates/schemas/` -- ignored
  by v1.
- `PreferencesConfig` at `src/nexus/config/settings.py:64-72` already
  exposes `github_repo: str = ""` and `github_branch: str = "main"`.
- `NexusPaths.templates_dir` at `paths.py:67-69` resolves to
  `~/.nexus/templates/`.
- Seed catalog at `templates/manifest.json` at the repo root with
  shape `{"version": "1.0", "generated": "2026-05-07", "templates":
  []}`.

Precedent to mirror: `GitHubReleasesClient` at
`src/nexus/updater/client.py:39-100` -- never-raises design, optional
`httpx.Client` injection for tests with `MockTransport`, logs failures
at `info` / `warning`. Tests use `transport_returning` /
`transport_raising` helpers at `tests/conftest.py:56-67`. The
established testing pattern is documented and stable.

## Key Insights

1. The feature is a faithful copy of the `GitHubReleasesClient`
   pattern with a different payload shape. Same "never-raises client
   returns Optional[Manifest]; orchestrator translates None into a
   user-facing error".
2. The wire payload and the cached payload are different shapes.
   Bolting `cached_at` onto a single `extra="forbid"` model breaks
   round-trip in both directions -- split into two models.
3. The fetch URL must be fully explicit. Convention is
   `https://raw.githubusercontent.com/<owner>/<name>/<branch>/<path>`
   where `<path>` defaults to `templates/manifest.json` but is
   configurable so an alternate registry layout does not require a
   code change.
4. `github_repo` empty is the only meaningful config-validation gate.
   Everything else (network, 404, malformed JSON, schema mismatch)
   shares the "log + return None + exit 1 with the underlying reason"
   code path.

## Recommendations

1. **Two Pydantic models** in `src/nexus/templates/models.py`:
   - `TemplateEntry(BaseModel)` with `name: str`, `template_type: str`
     (renamed from `type` to avoid the `type` keyword), `version: str`,
     `path: str` (within the repo), `checksum: str | None = None`.
     `model_config = ConfigDict(frozen=True, strict=True, extra="forbid")`.
   - `TemplateManifest(BaseModel)` -- the WIRE shape:
     `version: str`, `generated: str`, `templates: tuple[TemplateEntry, ...]`.
     Same frozen/strict/forbid config.
   - `CachedManifest(BaseModel)` -- the on-disk shape:
     `wire: TemplateManifest`, `cached_at: UtcDatetime`,
     `source: SyncSource` (frozen record of repo/branch/path used to
     fetch). Tracks "what we synced, when, and from where".
2. **`src/nexus/templates/registry.py`** -- `TemplateRegistry(templates_dir)`
   with `save_manifest(manifest: TemplateManifest, source: SyncSource) ->
   CachedManifest` (stamps `cached_at`) and
   `load_manifest() -> CachedManifest | None`. Atomic write via
   `tempfile + replace` matching `InstanceRegistry._atomic_write_to`.
3. **`src/nexus/templates/sync.py`** -- two classes side-by-side:
   - `GitHubTemplateClient` -- mirrors `GitHubReleasesClient`
     signature. `fetch_manifest(repo, branch, path) ->
     TemplateManifest | None`. Never raises. Logs `info` on the
     happy path, `warning` on non-200, `info` on network errors.
     Catches `ValidationError` from the wire-shape parse and returns
     None.
   - `GitHubSync` orchestrator -- wires client + registry + config.
     `run(repo: str, branch: str, path: str) -> SyncReport` returns
     a frozen dataclass with `outcome: Literal["ok", "no-config",
     "invalid-repo", "fetch-failed"]`, `manifest: CachedManifest |
     None`, `reason: str | None`. Validates `github_repo` shape via
     a new `_validate_github_repo` helper.
4. **`src/nexus/cli/commands_sync.py`** (new) -- mirrors
   `commands_setup.py` pattern. `@app.command sync()` is the Typer
   wrapper around `_sync_main(paths, config_manager, client,
   registry, console_out, console_err) -> int`. Maps `SyncReport` to
   Notice / Hint and an exit code.
5. **`nexus templates` command** wired in the same epic. Reads cached
   manifest via `TemplateRegistry.load_manifest()`. If `None`, prints
   a Hint pointing at `nexus sync`. Otherwise renders a Rich
   `DataTable` of name / type / version with a footer showing
   "synced X ago" via the existing `humanize_age` helper.
6. **`_validate_github_repo(value: str) -> str`** in
   `src/nexus/templates/sync.py`. Rejects URLs (`https://`,
   `http://`, `git@`), requires exactly one `/`, rejects empty
   components, strips trailing slashes. Returns the canonical
   `owner/name`. Raises a typed `InvalidGitHubRepoError` from
   `templates/errors.py` (new).

## Failure-mode handling

| Failure | Detection | Response |
|---|---|---|
| `github_repo` empty in config.yaml | `_sync_main` checks before calling client | `SyncReport(outcome="no-config")` -> `Notice.error("Template registry not configured")` + `Hint("Edit ~/.nexus/config.yaml: set github_repo to <owner>/<name>")`; exit 1 |
| `github_repo` is a URL or malformed | `_validate_github_repo` raises | `SyncReport(outcome="invalid-repo", reason="github_repo must be '<owner>/<name>', got: <input>")`; exit 1 |
| Network error / non-200 / 429 / malformed JSON / ValidationError | Client returns `None`, logs reason | `SyncReport(outcome="fetch-failed", reason=<from-log-context>)`; exit 1; cache untouched |
| Empty `templates: []` array | Pydantic accepts | Write to cache; `Notice.info("Catalog synced (0 templates available).")`; exit 0 |
| Disk full / unwritable cache | Registry raises `OSError` | Catch in orchestrator, return `SyncReport(outcome="fetch-failed", reason="cache write failed: <type>")`; exit 1 |
| `nexus templates` with no prior sync | `load_manifest()` returns `None` | Print `Hint("Run nexus sync to pull the template catalog.")`; exit 0 |
| `cached_at` round-trip | Two-model split (wire vs cached) | Wire model never sees `cached_at`; cached model always has it |
| Concurrent `nexus sync` invocations | tempfile + atomic replace | Last writer wins; both succeed without partial state. Acceptable for v1; documented in registry docstring |

## Trade-offs

| Decision | Pro | Con | Position |
|---|---|---|---|
| Two models (wire vs cached) | Honest separation, no round-trip break | Two classes instead of one | Take it (adversarial-review-driven) |
| Configurable manifest path | Doesn't lock the layout | Extra config field | Take it |
| Always re-fetch (no ETag) | One code path, simplest mental model | Less polite to GitHub later | Take it; revisit if rate limits bite |
| Default `github_repo = ""` | No coupling to a registry I don't own | First-run UX requires editing config.yaml | Take it; honest |
| `nexus templates` wired in same epic | Completes the user journey | ~30 LOC + one test file extra | Take it |
| `GitHubSync` co-located with client | Single-purpose module | Two abstractions in one file | Take it; both are sync-feature internals |
| Public repos only for v1 | No credential management | Private-fork users blocked | Take it; documented as a known limitation |

## Out of Scope

- Per-template YAML downloads (next epic: `2026.06-template-library`).
- Schema validation of template YAMLs against the empty
  `schemas/*.py` stubs.
- ETag / `If-None-Match` conditional GET.
- `--refresh` flag (always re-fetches today).
- GitHub auth / token support; private repos.
- Multi-registry support; diff / changelog between syncs.
- Auto-sync on startup or post-setup.
- Concurrent-write file locking (atomic rename is enough for v1).

## Open Questions

None blocking. All four design choices decided + four blocking
adversarial gaps closed.

## Adversarial Review

Reviewer flagged four blocking issues in v1; all closed in this
revision:

1. **Fetch URL ambiguity** -- `<repo>/<branch>/manifest.json` is
   wrong because the seed lives at `templates/manifest.json`. Closed
   by making the path component configurable and defaulting to
   `templates/manifest.json` (Recommendation 1 + failure-mode table).
2. **Round-trip serialization conflict** -- `cached_at` on the same
   `extra="forbid"` model as the wire payload breaks
   read-back. Closed by splitting into `TemplateManifest` (wire) and
   `CachedManifest` (on-disk wrapper) (Recommendation 1).
3. **`github_repo` format not validated** -- user could type a full
   URL. Closed by `_validate_github_repo` helper raising a typed
   `InvalidGitHubRepoError` (Recommendation 6 + failure-mode table).
4. **`nexus templates` crashes on missing cache** -- closed by
   explicit `if manifest is None` Hint branch (Recommendation 5).

Reviewer also flagged but classified non-blocking:

- 429 rate-limit handling -- client logs distinguishably, no special
  branch.
- Concurrent sync invocations -- atomic rename is sufficient.
- Private repo support -- explicitly out of scope; documented.
- UTC for `cached_at` -- enforced via project-wide `UtcDatetime`
  type.

## Research Findings Appendix

### Existing patterns

- `GitHubReleasesClient` at `src/nexus/updater/client.py:39-100`.
  Constructor signature:
  `__init__(self, *, repo, timeout_seconds=3.0, httpx_client=None)`.
  Tests inject `httpx_client=httpx.Client(transport=MockTransport(handler))`.
  Failure model: returns `None` on any failure; logs `info` for
  network, `warning` for non-200.
- `tests/conftest.py:56-67` -- `transport_returning(response)` and
  `transport_raising(exc)` helpers.
- `tests/test_updater_client.py` (mentioned in researcher brief) --
  13 tests covering happy path, 404, 403, timeout, malformed JSON,
  missing fields.

### Pydantic conventions

- `InstanceMeta` at `src/nexus/instances/models.py:33-90` uses
  `model_config = ConfigDict(frozen=True, strict=True,
  extra="forbid")` via the shared `_FROZEN` alias at line 18.
- `UtcDatetime` from `src/nexus/config/types.py` -- the project
  standard for timezone-aware datetimes (enforces UTC).

### Layer placement

- `src/nexus/templates/` is the natural home (replacing stubs).
- `src/nexus/cli/commands_sync.py` is new (mirrors the `commands_setup.py`
  pattern shipped yesterday).
- Help text edits go in `src/nexus/cli/help_text.py:417-426` (existing
  sync + templates entries marked as stubs).

## Session Notes

Assumptions-mode session. User confirmed all four recommended unclear
items (fail-fast on missing config, empty manifest is success, always
re-fetch, wire `nexus templates` in same epic). Adversarial agent
flagged four blocking gaps; all closed via two-model split,
configurable manifest path, repo-format validator, and explicit
no-cache branch in `nexus templates`. Estimated scope: ~750 LOC
across 6 new files + 2-3 modified.
