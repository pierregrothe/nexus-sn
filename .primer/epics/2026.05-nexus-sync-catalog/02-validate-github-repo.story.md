# Story 02: _validate_github_repo helper + InvalidGitHubRepoError

Status: done
Spec-Clarity: high
Depends-On: none

## Story

As `nexus sync`,
I want a typed validator that rejects anything other than an
`<owner>/<name>` slug before any HTTP fetch,
so that a user pasting `https://github.com/x/y` gets a clear error
instead of a silent 404 from the template registry.

## Acceptance Criteria

| Input                                | Expected                            | Notes                            |
|--------------------------------------|-------------------------------------|----------------------------------|
| `"owner/name"`                       | `Ok("owner/name")`                  | Canonical                        |
| `"Owner-A/repo_b.git"`               | `Ok("Owner-A/repo_b.git")`          | Hyphens/underscores/dots allowed |
| `"owner/name/"`                      | `Ok("owner/name")`                  | Trailing slash stripped          |
| `""`                                 | `Err("empty")`                      |                                  |
| `"   "`                              | `Err("empty")`                      | Whitespace-only                  |
| `"singleword"`                       | `Err("missing slash")`              |                                  |
| `"a/b/c"`                            | `Err("too many slashes")`           |                                  |
| `"/name"`                            | `Err("empty component")`            |                                  |
| `"owner/"`                           | `Err("empty component")`            |                                  |
| `"https://github.com/owner/name"`    | `Err("url not allowed")`            | https/http/git@ all rejected     |
| `"git@github.com:owner/name"`        | `Err("url not allowed")`            | SSH scheme                       |
| `"owner/name.git/"`                  | `Ok("owner/name.git")`              | Trailing slash stripped          |
| `" owner/name "`                     | `Ok("owner/name")`                  | Surrounding whitespace stripped  |

AC1: Each `Err` variant raises `InvalidGitHubRepoError` whose
`reason` attribute is one of the slugs above. Callers can map the
slug to a Notice / Hint without parsing the message string.

## Must NOT

- Must NOT touch the network. Pure string validation.
- Must NOT return `Result[str, str]`. The project's convention is to
  raise a typed exception (per `validate_baseline_name` /
  `validate_profile_name`).
- Must NOT silently rewrite or coerce inputs (e.g., dropping a
  leading `https://`); reject them so the user fixes their config.

## Tasks / Subtasks

- [ ] Create `src/nexus/templates/errors.py` (AC: 1)
  - [ ] `class TemplatesError(Exception)`: base
  - [ ] `class InvalidGitHubRepoError(TemplatesError)`: carries
        `value` + `reason` attributes; one-line error message
- [ ] Create `src/nexus/templates/repo_name.py` (AC table)
  - [ ] `def validate_github_repo(value: str) -> str`
  - [ ] Strip surrounding whitespace; strip trailing slash; reject
        empty / whitespace-only -> "empty"
  - [ ] Reject `https://`, `http://`, `git@` -> "url not allowed"
  - [ ] Require exactly one `/`; reject 0 -> "missing slash", >1 ->
        "too many slashes"
  - [ ] Reject either component being empty -> "empty component"
  - [ ] Module-level `__all__` includes the function
- [ ] Re-export from `src/nexus/templates/__init__.py`
- [ ] Create `tests/test_templates_repo_name.py`
  - [ ] Parametrized happy-path tests (Ok rows)
  - [ ] Parametrized rejection tests (Err rows) -- assert
        `excinfo.value.reason == "<expected slug>"`
  - [ ] `test_validate_github_repo_error_message_includes_value_and_reason`

## Existing Code

Greenfield. No callers yet; story 05 (orchestrator) will use it.

## Dev Notes

### Modules Affected

- `src/nexus/templates/errors.py` (new)
- `src/nexus/templates/repo_name.py` (new)
- `src/nexus/templates/__init__.py` (re-export)
- `tests/test_templates_repo_name.py` (new)

### Testing Approach

- Pure-function tests. Function-based naming.
- Parametrize the AC table directly.

### Conventions

- Mirror `validate_profile_name` (story 03 of the setup epic).

## References

- Brainstorming: `.primer/brainstorming/2026-05-18-nexus-sync-catalog.md`
  Recommendation 6 + adversarial-review item 3
- Precedent: `src/nexus/instances/profile_name.py`
