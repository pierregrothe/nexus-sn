# Story 03: GitHubTemplateClient (raw.githubusercontent.com fetch)

Status: done
Spec-Clarity: high
Depends-On: 01

## Story

As `nexus sync`,
I want a never-raising HTTP client that fetches a manifest from a
configurable raw-GitHub URL,
so that every error variant (network down, 404, 403, malformed JSON,
schema mismatch) routes through the same "return None, log a reason"
contract the orchestrator already expects.

## Acceptance Criteria

AC1:
**Given** a `MockTransport` that responds 200 with the seed manifest
**When** `GitHubTemplateClient.fetch_manifest("owner/name", "main",
"templates/manifest.json")` is called
**Then** it returns a `TemplateManifest` with the expected version
/ generated / templates and the request URL was
`https://raw.githubusercontent.com/owner/name/main/templates/manifest.json`.

AC2:
**Given** the transport returns 404
**When** `fetch_manifest` is called
**Then** it returns `None` and logs a `warning` containing the
status code.

AC3:
**Given** the transport raises `httpx.ConnectError`
**When** `fetch_manifest` is called
**Then** it returns `None` and logs an `info` containing the exc
type name.

AC4:
**Given** the transport returns 200 but the body is malformed JSON
**When** `fetch_manifest` is called
**Then** it returns `None` and logs an `info` containing
`"invalid JSON"`.

AC5:
**Given** the transport returns 200 + valid JSON that fails
`TemplateManifest.model_validate_json` (e.g., missing `version`)
**When** `fetch_manifest` is called
**Then** it returns `None` and logs an `info` containing the first
ValidationError loc.

AC6:
**Given** the transport returns 429
**When** `fetch_manifest` is called
**Then** it returns `None` and logs a `warning` whose message
distinguishably mentions `"rate limit"`.

AC7: The class accepts an optional `httpx.Client` constructor kwarg
for tests. When `None`, builds its own with `timeout=10.0`. Matches
the `GitHubReleasesClient` injection style.

## Must NOT

- Must NOT raise from `fetch_manifest`. Tests grep the source file
  for `raise` outside the docstring; only `raise` should be inside
  `try/except` blocks that catch and convert to `None`.
- Must NOT send any auth headers. v1 is anonymous-only.
- Must NOT depend on the `nexus.cli` layer (HTTP client is a leaf).
- Must NOT log the response body even on failure (privacy / size).

## Tasks / Subtasks

- [ ] Create `src/nexus/templates/sync.py` (this story adds the
      client only; story 05 adds the orchestrator to the same file)
  - [ ] File header + Google docstrings + `__all__`
  - [ ] `class GitHubTemplateClient` with `__init__(self, *,
        httpx_client: httpx.Client | None = None, timeout_seconds:
        float = 10.0)`
  - [ ] `fetch_manifest(repo, branch, path) -> TemplateManifest | None`
  - [ ] URL: `f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"`
  - [ ] Catch `httpx.HTTPError` -> log info -> return None
  - [ ] Branch on `response.status_code`: 200 -> parse;
        429 -> log warning "rate limit"; else log warning + status
  - [ ] Parse: `json.JSONDecodeError` -> info "invalid JSON" + None;
        `ValidationError` -> info with first loc + None
  - [ ] No bare `except:`
- [ ] Tests in `tests/test_templates_github_client.py`
  - [ ] `test_fetch_manifest_returns_parsed_manifest_on_200`
  - [ ] `test_fetch_manifest_url_includes_repo_branch_and_path`
  - [ ] `test_fetch_manifest_returns_none_on_404`
  - [ ] `test_fetch_manifest_returns_none_on_403`
  - [ ] `test_fetch_manifest_returns_none_on_429_logs_rate_limit`
  - [ ] `test_fetch_manifest_returns_none_on_connect_error`
  - [ ] `test_fetch_manifest_returns_none_on_malformed_json`
  - [ ] `test_fetch_manifest_returns_none_on_schema_mismatch`
  - [ ] `test_fetch_manifest_accepts_empty_templates_array`
  - [ ] `test_fetch_manifest_default_timeout_is_10_seconds`

## Existing Code

- Mirror `src/nexus/updater/client.py:39-100` constructor /
  fetch-method shape. Same injection pattern, same logging levels.
- Use `transport_returning` / `transport_raising` helpers from
  `tests/conftest.py:56-67`.

## Dev Notes

### Modules Affected

- `src/nexus/templates/sync.py` (new -- this story creates the file)
- `tests/test_templates_github_client.py` (new)

### Testing Approach

- `httpx.MockTransport` driven by handler closures.
- Use `caplog` fixture for log-content assertions.
- Function-based test naming.

### Conventions

- See `~/.claude/rules/no-mocks.md`, `~/.claude/rules/python-314.md`
  (multi-except form for the JSON+ValidationError catch).

## References

- Brainstorming: `.primer/brainstorming/2026-05-18-nexus-sync-catalog.md`
  Recommendation 3, Failure-mode table
- Precedent: `src/nexus/updater/client.py`,
  `tests/test_updater_client.py`
