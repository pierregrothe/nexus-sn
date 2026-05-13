# README Sync -- Design Spec

Date: 2026-05-13
Status: approved

## Problem

README.md contains several values derived from live project state
(version, Python requirement, test count) that go stale between milestones.
Currently these are hand-maintained and frequently lag the actual code.

## Goals

- Auto-update three README fields on every `/primer sync` run: version,
  Python requirement, test count.
- Warn (but not auto-rewrite) when the stub-commands list in README diverges
  from `NotImplementedError` occurrences in `cli.py`.
- Zero new dependencies. Uses stdlib `tomllib` (3.11+) and `subprocess`.
- Test coverage at 100% line coverage, consistent with project standards.

## Non-Goals

- Auto-rewriting the implemented/stub command prose bullet lists.
- Syncing any other README sections (Mermaid diagrams, Quick Start, etc.).
- Running on every commit (pre-commit hook out of scope).

## Architecture

### Component: `scripts/sync-readme.py`

Standalone script. No imports from `src/nexus/`. Runnable directly:
`python scripts/sync-readme.py` (exits 0 on success, 1 on error).

#### Data sources

| Field | Source | Parse method |
|---|---|---|
| version | `pyproject.toml [tool.poetry] version` | `tomllib.load()` |
| python_req | `pyproject.toml [tool.poetry.dependencies] python` | `tomllib.load()`, strip leading `^>=~` |
| test_count | `pytest --collect-only -q` | regex on last stdout line |
| stub_commands | `src/nexus/cli.py` | regex for `raise NotImplementedError` near `@app.command()` |

#### README anchor strategy

Two anchor styles are used:

1. **Line-match anchors** (version, Python req): replace the entire matching
   line. No markers inserted into README.

   - Version: first line matching `^CalVer:` anywhere in README.
   - Python req: first line matching `^- Python ` under `## Requirements`.

2. **Comment anchors** (test count): a single-line HTML comment pair that
   is invisible in rendered GitHub markdown:

   ```markdown
   <!-- tests -->824 tests passing, all real fakes, no mocks.<!-- /tests -->
   ```

   On first run, if no `<!-- tests -->` marker exists, the script inserts
   this line immediately after the `## What is implemented` heading.
   On subsequent runs it replaces the content between the markers.

#### Stub-mismatch warning

The script greps `src/nexus/cli.py` for function names immediately followed
(within 10 lines) by `raise NotImplementedError`. It then checks whether the
README "stubs" bullet list contains the same set of names. If they diverge,
it prints a warning to stdout and exits with code 0 (warning, not error):

```
WARN: stub mismatch -- cli.py: setup, sync | README: setup, sync, templates, assess
      Update the 'stubs' bullet list in README manually.
```

#### Exit codes

- `0` -- success (including stub mismatch warnings)
- `1` -- pyproject.toml not found, pytest not available, or README not found

### Primer skill extension

One step appended to the end of the Sync section in
`~/.claude/skills/primer/SKILL.md`:

> **Step 8: Project README sync (if applicable)**
> If `scripts/sync-readme.py` exists at the project root, run:
> `python scripts/sync-readme.py`
> Report what fields changed or "README already up to date."

This step is a no-op on projects without the script. No other changes to
the primer skill.

## README changes required

Before the script is useful, README.md needs two changes:

1. `CalVer: YYYY.0M.PATCH` -- update to actual current version (`2026.05.1`).
   The script will keep it current from that point on.
2. The `<!-- tests -->` anchor line is inserted automatically on first run --
   no manual README edit needed for test count.

## Testing

File: `tests/test_sync_readme.py`

Test cases:
- `test_sync_readme_updates_version` -- version line replaced correctly
- `test_sync_readme_updates_python_req` -- python req line replaced correctly
- `test_sync_readme_inserts_test_count_first_run` -- inserts anchor+count
  when marker absent
- `test_sync_readme_updates_test_count_subsequent_run` -- replaces existing
  count between markers
- `test_sync_readme_no_change_when_already_current` -- idempotent, no file
  write when values match
- `test_sync_readme_warns_on_stub_mismatch` -- prints WARN and exits 0
- `test_sync_readme_exits_1_if_readme_missing` -- error path

All tests use `tmp_path` fixtures with minimal README templates.
No mocks. `pytest` subprocess call is faked via a `FakePytest` callable
(a `@dataclass(slots=True)` that returns canned stdout, injected as a
parameter so tests never spawn a real subprocess).

Note: `scripts/sync-readme.py` lives outside `src/nexus/` and is not
tracked by the coverage ratchet. The test file itself is under `tests/`
and is subject to the normal 100% line coverage requirement.

## File layout

```
scripts/
  sync-readme.py         -- the sync script (new)
tests/
  test_sync_readme.py    -- 7 test functions (new)
~/.claude/skills/primer/SKILL.md -- one step added to Sync section (dotfiles)
```

## Sequence on /primer sync

```
/primer sync invoked
  -> Step 1-7: existing .primer/ file updates
  -> Step 8: python scripts/sync-readme.py
       reads pyproject.toml (tomllib)
       runs pytest --collect-only -q (subprocess)
       reads README.md
       writes README.md with updated fields
       prints changed field summary
```
