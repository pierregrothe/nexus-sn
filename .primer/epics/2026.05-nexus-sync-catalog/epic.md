# Epic: nexus sync v1 (catalog index)

Phase: 2026.05-setup-sync
Status: planned

## Goal

Ship `nexus sync` as a fail-fast catalog-index fetcher that pulls a
manifest from a configurable GitHub repo, caches it under
`~/.nexus/templates/manifest.json`, and powers a working `nexus
templates` listing. Per-template downloads and apply remain in a
future epic.

## Source

- Brainstorming: `../../brainstorming/2026-05-18-nexus-sync-catalog.md`
- Roadmap phase: `2026.05-setup-sync`, items `githubsync` +
  `templateregistry` + the `nexus sync` / `nexus templates` slots in
  `commands_top.py`.

## Requirements Inventory

### Functional Requirements

- FR1 (config gate): `nexus sync` exits 1 with an actionable Hint
  when `github_repo` is empty. [Source: brainstorming
  Failure-mode-row-1]
- FR2 (repo-shape validation): `github_repo` must be `<owner>/<name>`;
  URLs and malformed inputs are rejected before any HTTP. [Source:
  Failure-mode-row-2, Recommendation 6]
- FR3 (anonymous fetch): client GETs
  `https://raw.githubusercontent.com/<owner>/<name>/<branch>/<path>`
  with a configurable `path` (default `templates/manifest.json`).
  Never raises; returns `None` on any failure. [Source:
  Recommendation 3]
- FR4 (atomic cache write): registry writes the cached manifest via
  tempfile + rename. A failed write never leaves the previous cache
  in a partial state. [Source: Recommendation 2]
- FR5 (empty catalog is success): a manifest with `templates: []` is
  written to the cache and `nexus sync` exits 0 with an info Notice.
  [Source: Failure-mode-row-4]
- FR6 (orchestrator outcome record): `GitHubSync.run` returns a
  frozen `SyncReport` with `outcome`, `manifest`, `reason` so the
  command layer maps it cleanly to exit codes + console output.
  [Source: Recommendation 3]
- FR7 (no-cache hint): `nexus templates` invoked before any `nexus
  sync` prints a Hint pointing at sync. Does not crash. [Source:
  Recommendation 5 + adversarial-review item 4]
- FR8 (cached listing): `nexus templates` invoked after a successful
  sync renders a Rich `DataTable` of name / type / version with a
  "synced X ago" footer. [Source: Recommendation 5]

### Non-Functional Requirements

- NFR1: 0 errors mypy strict + pyright strict. [CLAUDE.md]
- NFR2: No `unittest.mock`. Tests use `httpx.MockTransport` and the
  existing conftest helpers. [.claude/rules/no-mocks.md]
- NFR3: Python 3.14 syntax. [.claude/rules/python-314.md]
- NFR4: All new Pydantic models use
  `ConfigDict(frozen=True, strict=True, extra="forbid")`. [CLAUDE.md]
- NFR5: ASCII only. File headers + Google docstrings + `__all__`.
- NFR6: File-size cap 800 src / 1400 tests. [ADR-023]
- NFR7: `cached_at` is `UtcDatetime` (UTC enforced project-wide).
  [.claude/rules/utc-timezone.md]

### Constraints

- C1: Public repos only for v1; no GitHub auth / token support.
  [Brainstorming Out-of-Scope]
- C2: Wire payload (`TemplateManifest`) and cached payload
  (`CachedManifest`) are separate models -- no `extra="forbid"`
  round-trip break.

## Stories

| #  | Title                                                     | Clarity | Depends-On | Status  |
|----|-----------------------------------------------------------|---------|------------|---------|
| 01 | TemplateEntry + TemplateManifest + CachedManifest models  | high    | none       | backlog |
| 02 | _validate_github_repo + InvalidGitHubRepoError            | high    | none       | backlog |
| 03 | GitHubTemplateClient (raw.githubusercontent.com fetch)    | high    | 01         | backlog |
| 04 | TemplateRegistry (atomic save_manifest + load_manifest)   | high    | 01         | backlog |
| 05 | GitHubSync orchestrator + SyncReport                      | high    | 01, 02, 03, 04 | backlog |
| 06 | nexus sync command (commands_sync.py)                     | high    | 05         | backlog |
| 07 | nexus templates command (DataTable + no-cache Hint)       | high    | 04         | backlog |

## Coverage Map

- FR1 -> 05, 06
- FR2 -> 02, 05, 06
- FR3 -> 03
- FR4 -> 04
- FR5 -> 01, 04, 05
- FR6 -> 05
- FR7 -> 07
- FR8 -> 07
- NFR1..7 -> all stories
- C1, C2 -> 01, 03

## Existing Code Reused (delta-only)

- `src/nexus/updater/client.py:39-100` (`GitHubReleasesClient`) ->
  copied pattern (constructor, fetch method, never-raises). Not
  shared via inheritance; sync needs different payload shape.
- `src/nexus/instances/registry.py:_atomic_write_to` -> mirrored in
  `TemplateRegistry`.
- `src/nexus/cli/commands_setup.py` pattern -> mirrored in
  `commands_sync.py` (Typer wrapper + `_main` testable helper).
- `tests/conftest.py:56-67` (`transport_returning`,
  `transport_raising`) -> reused.
- `src/nexus/config/types.py:UtcDatetime` -> field type for
  `cached_at`.

## Progress

- Stories: 0/7 done, 0 in-progress, 7 backlog
