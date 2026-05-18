# Story 05: GitHubSync orchestrator + SyncReport

Status: done
Spec-Clarity: high
Depends-On: 01, 02, 03, 04

## Story

As `nexus sync` (the Typer command),
I want a single `run()` method that returns a typed `SyncReport`
covering every outcome,
so that the command layer never has to do a try/except chain --
just match on `report.outcome` and render.

## Acceptance Criteria

AC1 (config gate):
**Given** `github_repo == ""` (the project default)
**When** `GitHubSync(...).run(repo="", branch="main",
path="templates/manifest.json")` is called
**Then** it returns `SyncReport(outcome="no-config", manifest=None,
reason=<actionable>)`. No HTTP is issued.

AC2 (invalid repo shape):
**Given** `github_repo == "https://github.com/x/y"`
**When** `run(...)` is called
**Then** it returns `SyncReport(outcome="invalid-repo",
manifest=None, reason="...url not allowed...")`. No HTTP is issued.

AC3 (happy path):
**Given** the client returns a `TemplateManifest`
**When** `run(...)` is called with a valid repo
**Then** the registry writes the cache; the report is
`SyncReport(outcome="ok", manifest=<CachedManifest>, reason=None)`.

AC4 (fetch failed):
**Given** the client returns `None`
**When** `run(...)` is called
**Then** the report is `SyncReport(outcome="fetch-failed",
manifest=None, reason="fetch failed (see logs)")`. The cache file is
not touched.

AC5 (empty catalog):
**Given** the client returns a `TemplateManifest` with `templates=()`
**When** `run(...)` is called
**Then** the registry writes it and `outcome="ok"`. Empty catalog is
not an error.

AC6 (registry write error):
**Given** the client succeeds but the registry raises `OSError`
**When** `run(...)` is called
**Then** the report is `SyncReport(outcome="fetch-failed",
manifest=None, reason="cache write failed: <ExcType>")`. Any prior
cache is preserved.

## Must NOT

- Must NOT print to console. Pure logic; the command layer renders.
- Must NOT call `sys.exit`. Return the report; let the command map
  to an exit code.
- Must NOT catch `Exception` in a wide block. Narrow exceptions
  only.
- Must NOT instantiate `httpx.Client` or open files itself --
  collaborators are injected.

## Tasks / Subtasks

- [ ] Append `SyncReport` frozen dataclass + `GitHubSync` class to
      `src/nexus/templates/sync.py` (same file as the client)
  - [ ] `_OutcomeT = Literal["ok", "no-config", "invalid-repo", "fetch-failed"]`
  - [ ] `@dataclass(frozen=True, slots=True) class SyncReport`:
        outcome, manifest (`CachedManifest | None`), reason
        (`str | None`)
  - [ ] `class GitHubSync:` constructor takes `client:
        GitHubTemplateClient`, `registry: TemplateRegistry`
  - [ ] `run(repo, branch, path) -> SyncReport`:
        1. If repo empty -> no-config
        2. Validate repo via `validate_github_repo` ->
           InvalidGitHubRepoError caught -> invalid-repo
        3. `client.fetch_manifest(canonical_repo, branch, path)`
           returns None -> fetch-failed
        4. `registry.save_manifest(manifest, SyncSource(...))`
           catches OSError -> fetch-failed (reason mentions cache
           write)
        5. Return ok with the CachedManifest
- [ ] Update `src/nexus/templates/__init__.py` to re-export
      `GitHubSync` and `SyncReport`
- [ ] Tests in `tests/test_templates_github_sync.py`
  - [ ] `test_run_returns_no_config_when_repo_empty`
  - [ ] `test_run_returns_invalid_repo_on_url_input`
  - [ ] `test_run_returns_fetch_failed_when_client_returns_none`
  - [ ] `test_run_returns_ok_with_cached_manifest_on_happy_path`
  - [ ] `test_run_accepts_empty_templates_array_as_ok`
  - [ ] `test_run_returns_fetch_failed_when_registry_raises_oserror`
  - [ ] `test_run_preserves_previous_cache_on_fetch_failure`

## Existing Code

- Composes story 01 (models), 02 (validator), 03 (client), 04
  (registry). No reuse from outside the templates/ subpackage.

## Dev Notes

### Modules Affected

- `src/nexus/templates/sync.py` (append)
- `src/nexus/templates/__init__.py` (re-export)
- `tests/test_templates_github_sync.py` (new)

### Testing Approach

- Build a minimal stub `GitHubTemplateClient` subclass that returns a
  pre-canned manifest or None. NOT a mock -- a real subclass
  satisfying the Protocol.
- For the registry-OSError test, use a real `TemplateRegistry` with
  `monkeypatch.setattr(Path, "replace", lambda *a, **kw: (_ for _ in
  ()).throw(OSError("disk full")))` -- still no mock library.

### Conventions

- See `~/.claude/rules/refactoring.md` (grep callers before changing
  signatures -- none here, all new symbols).

## References

- Brainstorming: Recommendation 3, Failure-mode table
- Precedent: `src/nexus/cli/commands_setup.py:_setup_main` for the
  "return a report, let the caller render" idiom
