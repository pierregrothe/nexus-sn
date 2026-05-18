# Story 03: validate_profile_name() input validator

Status: backlog
Spec-Clarity: high
Depends-On: none

## Story

As a NEXUS user typing a profile name into the wizard,
I want names containing path-traversal sequences, separators, or
excessive length to be rejected before they ever reach
`InstanceRegistry.register`,
so that a typo or malicious paste cannot write `meta.json` outside
`~/.nexus/instances/`.

## Acceptance Criteria

| Input                               | Expected             | Notes                                |
|-------------------------------------|----------------------|--------------------------------------|
| `"prod"`                            | `Ok("prod")`         | Simple alphanumeric                  |
| `"prod-east-1"`                     | `Ok("prod-east-1")`  | Dashes allowed                       |
| `"prod_team_a"`                     | `Ok("prod_team_a")`  | Underscores allowed                  |
| `"Prod1"`                           | `Ok("Prod1")`        | Mixed case allowed                   |
| `""`                                | `Err("empty")`       | Empty rejected                       |
| `"   "`                             | `Err("empty")`       | Whitespace-only rejected             |
| `"prod team"`                       | `Err("whitespace")`  | Spaces rejected                      |
| `"../prod"`                         | `Err("traversal")`   | Parent-dir attempt                   |
| `"prod/.."`                         | `Err("traversal")`   | Anywhere in string                   |
| `"prod\\east"`                      | `Err("separator")`   | Backslash (Windows path sep)         |
| `"prod/east"`                       | `Err("separator")`   | Forward slash                        |
| `".hidden"`                         | `Err("leading dot")` | Hidden-file convention forbidden     |
| `"a" * 65`                          | `Err("too long")`    | Cap at 64 chars                      |
| `"a" * 64`                          | `Ok("a" * 64)`       | Exactly 64 is allowed                |
| `"prod\xe9"` (any non-ASCII)        | `Err("non-ascii")`   | ASCII-only project rule              |
| `"prod\x00null"`                    | `Err("control")`     | Embedded NUL                         |

AC1: Each `Err` variant returns a distinct, hint-ready string. The
calling code (story 06) wraps it in a Notice telling the user the
allowed character set.

## Must NOT

- Must NOT mutate input (no lowercasing, no `.strip()` returned -- if
  the input has leading/trailing whitespace, reject with `"whitespace"`).
- Must NOT depend on the filesystem (no `Path(...)` calls; pure string
  validation).
- Must NOT raise -- returns `Result` only. Exceptions are for unexpected
  failures, not user input.
- Must NOT use a regex if a clearer explicit check works (Python 3.14
  `match/case` over character classes is fine).

## Tasks / Subtasks

- [ ] Create `src/nexus/instances/profile_name.py` (AC: 1)
  - [ ] Function signature:
        `def validate_profile_name(name: str) -> Result[str, str]`
  - [ ] Check order: empty -> whitespace -> length -> traversal ->
        separator -> leading-dot -> non-ascii -> control-char -> ok
  - [ ] Define `_MAX_LENGTH = 64` and `_ALLOWED_RE = ...` (or per-char
        check) as module constants
  - [ ] `__all__ = ["validate_profile_name"]`
- [ ] Create `tests/test_instances_profile_name.py` (AC: 1)
  - [ ] `TestValidateProfileName` class with one test per row of the
        AC table
  - [ ] Parametrize via `pytest.mark.parametrize` where the same
        assertion shape repeats (Ok cases vs Err cases)

## Existing Code

Greenfield. No callers yet -- story 06 will call this from the wizard
helper before `InstanceRegistry.register`.

## Dev Notes

### Modules Affected

- `src/nexus/instances/profile_name.py` (new)
- `tests/test_instances_profile_name.py` (new)

### Testing Approach

- Pure-function unit tests, no fakes needed.
- Parametrized class-based tests for the table.
- Verify `Err` payloads are stable strings so callers can map to
  user-facing hints (snapshot the string values in the test).

### Conventions

- File header, Google docstrings, `__all__`.
- ASCII only.
- Frozen / `slots=True` not applicable (function, not class).

## References

- Brainstorming: `.primer/brainstorming/2026-05-18-nexus-setup-credential-wizard.md`,
  section "Failure-mode handling" row 5
- Rule: `~/.claude/rules/ascii-only.md`
