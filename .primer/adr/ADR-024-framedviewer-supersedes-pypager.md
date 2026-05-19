# ADR-024: FramedViewer (Textual) supersedes pypager for sticky-frame paging

**Status:** accepted
**Date:** 2026-05-18
**Enforcement:** none

## Context

PRD-001 (`.primer/prd/PRD-001-cli-ux-wow-factor.md`), authored
2026-05-15, declared in its Out-of-Scope fence that "We will NOT
add Textual as a dependency. The TUI app paradigm is wrong for
one-shot CLI commands." The PRD's in-scope design was a custom
`PagedTable` component backed by `pypager` (pure-Python pager,
~5 KB) plus a four-tier `RenderProfile` substrate.

Commit `8528230` (2026-05-16) -- the same commit that introduced
the PRD itself -- added `textual = "^8.2.6"` to `pyproject.toml`
and shipped `src/nexus/ui/components/framed_viewer.py`, a full
Textual `App` with sticky header / footer, virtual-scroll body,
`/` inline filter, sort, `r` refresh, `Enter` for row-detail
modal, and `y` clipboard copy. Both `nexus plugins list` and
`nexus plugins outdated` route to `FramedViewer` via
`_emit_framed_view` on RICH/BASIC profiles.

`PagedTable`, `PagerProtocol`, and `PypagerPager` shipped in the
same commit at 100% coverage but never gained a consumer. The
PRD-vs-code divergence was not recorded in `decisions.md`, any
ADR, or `governance.md` -- discovered during the 2026-05-18
brainstorm + adversarial review (see
`.primer/brainstorming/2026-05-18-cli-ux-implementation-plan.md`).

The choice between the two architectures must be adjudicated:
either FramedViewer is rolled back to honor PRD-001 v1, or
PRD-001 is reconciled with FramedViewer reality and the unused
pypager / PagedTable surface is deleted.

## Decision

FramedViewer (Textual) is the canonical sticky-frame paging path
for `nexus plugins list` and `nexus plugins outdated`. PRD-001
is revised (v2, 2026-05-18) to remove the Textual ban and to
declare pypager / PagedTable / PagerProtocol / PypagerPager
superseded.

The following are deleted from the codebase:

* `src/nexus/ui/components/paged_table.py`
* `src/nexus/ui/components/pager.py`
* `tests/test_paged_table.py`
* `tests/fakes/pager.py`
* `pypager = "^3.0.1"` in `pyproject.toml`
* Ratchet baselines for `nexus.ui.components.paged_table` and
  `nexus.ui.components.pager`

The `nexus status` Terminal panel's `Pager` row label changes
from `pypager` to `framed` to reflect reality.

## Consequences

* One runtime dependency removed (pypager). Install footprint
  shrinks.
* Two source modules + two test modules deleted (~250 LOC).
* Single canonical paging implementation eliminates the long-term
  risk of two parallel paging paths diverging.
* Textual is locked in as a NEXUS runtime dep. Future TUI
  features (e.g. `nexus tui`) can build on it without a new
  ADR; the architectural decision is recorded here.
* PRD-vs-code divergences must be caught by the brainstorm flow
  going forward. The PRD anti-creep fence is only load-bearing
  if reconciled when code lands.
* `LEGACY` / `PLAIN` profile fallback continues to use the inline
  `DataTable` path via `_emit_inline_view` -- the deletion does
  not affect non-Textual profiles.
