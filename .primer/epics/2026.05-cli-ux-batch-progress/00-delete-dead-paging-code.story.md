# Story 00: Delete pypager + PagedTable + Pager dead code

Status: done
Spec-Clarity: high
Depends-On: none

## Story

As a NEXUS maintainer,
I want to delete the pypager + PagedTable + PagerProtocol +
PypagerPager modules that ship at 100% coverage but have zero
consumers,
so that the codebase has a single canonical paging path
(FramedViewer) and the runtime dep list shrinks.

## Acceptance Criteria

AC1 (modules deleted):
**Given** main has `src/nexus/ui/components/paged_table.py` and
`src/nexus/ui/components/pager.py`
**When** Story 00 ships
**Then** both files are removed; grep for `PagedTable`,
`PagerProtocol`, `PypagerPager` returns zero matches in `src/`.

AC2 (test files deleted):
**Given** there exist test modules covering the deleted source
**When** Story 00 ships
**Then** the corresponding `tests/test_paged_table*.py` and
`tests/test_pager*.py` files are removed.

AC3 (reexports removed):
**Given** `src/nexus/ui/components/__init__.py` re-exports the
deleted types
**When** Story 00 ships
**Then** `PagedTable`, `PagerProtocol`, `PypagerPager` are absent
from `__all__` and from the import block.

AC4 (ratchet baselines removed):
**Given** `.ratchet.json` contains
`nexus.ui.components.paged_table` and
`nexus.ui.components.pager` entries
**When** Story 00 ships
**Then** both entries are absent from `.ratchet.json`.

AC5 (dep removed):
**Given** `pyproject.toml` line 25 pins `pypager = "^3.0.1"`
**When** Story 00 ships
**Then** the dep is removed; `poetry lock` is re-run; `poetry.lock`
no longer references `pypager`.

AC6 (no regressions):
**Given** the full test suite (1303 tests baseline)
**When** Story 00 lands
**Then** the suite still passes; coverage gate still passes;
pyright + mypy + ruff + black all report 0 errors.

AC7 (ADR drafted):
**Given** there is no governance record of the FramedViewer
reversal
**When** Story 00 ships
**Then** `.primer/adr/ADR-NNN-framedviewer-supersedes-pypager.md`
exists with Status: proposed (finalized to Accepted in Story 05).
Content covers: context (PRD-001 v1 ban broken by commit
`8528230`), decision (FramedViewer is canonical, pypager dead),
consequences (1 dep removed, ~250 LOC dead-code removed).

## Must NOT

* Must NOT delete `framed_viewer.py`, `paged_table.py`'s SIBLING
  components, or any other shipped UI module. Only the three named
  modules are dead.
* Must NOT rename or refactor the surviving components.
* Must NOT delete the brainstorming or PRD artifacts that referenced
  PagedTable -- those are historical record.

## Tasks / Subtasks

* [ ] Grep verification: `grep -rn "PagedTable\|PagerProtocol\|
      PypagerPager" src/ tests/` returns only the to-delete files
      and their tests
* [ ] Delete `src/nexus/ui/components/paged_table.py`
* [ ] Delete `src/nexus/ui/components/pager.py`
* [ ] Delete test files (whichever exist):
  * [ ] `tests/test_paged_table.py` or similar
  * [ ] `tests/test_pager.py` or similar
* [ ] Edit `src/nexus/ui/components/__init__.py`: remove the
      three imports + `__all__` entries
* [ ] Edit `.ratchet.json`: remove the two baselines
* [ ] Edit `pyproject.toml`: remove `pypager = "^3.0.1"` line
* [ ] Run `poetry lock`; commit refreshed `poetry.lock`
* [ ] Run `pytest` to verify zero regressions
* [ ] Run `pyright src/` and `mypy src/nexus/ --strict` -- both 0
* [ ] Run `ruff check` and `black --check src/ tests/` -- both 0
* [ ] Draft `.primer/adr/ADR-NNN-framedviewer-supersedes-pypager.md`:
  * [ ] Status: proposed
  * [ ] Context: PRD-001 v1 (2026-05-15) banned Textual; commit
        `8528230` (2026-05-16) silently added it; PRD-001 v2
        (2026-05-18) reconciled. Recording the reversal.
  * [ ] Decision: FramedViewer is canonical sticky-frame paging.
        pypager removed.
  * [ ] Consequences: -1 runtime dep, -~250 LOC, single paging
        implementation.

## Existing Code

Files to delete (canonical inventory):
* `src/nexus/ui/components/paged_table.py`
* `src/nexus/ui/components/pager.py`
* matching test files

Files to edit (surgical):
* `src/nexus/ui/components/__init__.py`
* `.ratchet.json`
* `pyproject.toml`
* `poetry.lock` (regenerated)

ADR to create:
* `.primer/adr/ADR-NNN-framedviewer-supersedes-pypager.md` (NNN =
  next free ADR number)

## Dev Notes

### Verifying "zero consumers" before deletion

```
grep -rn "PagedTable\|PagerProtocol\|PypagerPager\|pypager" \
  src/ tests/ scripts/ docs/ pyproject.toml
```

Expected matches: the three to-delete source files, their test
files, the pyproject pin, and historical references in `.primer/`
(those stay -- record of history). No live consumers.

### ADR numbering

Run `ls .primer/adr/ | sort` to find next free number. Use that
number in the filename.

## References

* Brainstorming pivot:
  `.primer/brainstorming/2026-05-18-cli-ux-implementation-plan.md`
* PRD-001 v2:
  `.primer/prd/PRD-001-cli-ux-wow-factor.md` (revision history
  section + dead-code-deletion subsection)
* No-backward-compat rule:
  `C:/Users/pierre/.claude/rules/no-backward-compat.md`
* Surgical-changes rule:
  `C:/Users/pierre/.claude/rules/surgical-changes.md`
