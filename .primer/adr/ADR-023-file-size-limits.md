# ADR-023: File Size Limits

**Status:** accepted
**Date:** 2026-05-16
**Enforcement:** hook (pre-commit + post-edit, ratchet from baseline)

## Context

The codebase has organically grown a few modules well past the point where they can be reasoned about as a single unit:

- ``src/nexus/cli.py`` is 4478 lines (89 commands, 30+ helpers).
- ``src/nexus/plugins/executor.py`` is 854 lines.

Long files dilute single-responsibility, slow code review (no
reviewer reads 4000 lines carefully), and make the file-headers
rule meaningless (one-line "description" cannot honestly summarise
a 4000-line module).

A hard ceiling was discussed and agreed:
- **800 lines** for production modules under ``src/nexus/``.
- **1000 lines** for test modules under ``tests/``.

Tests get a higher cap because pytest files often group many small
scenario tests around a single subject, and splitting them just to
satisfy line counts hurts navigability.

## Decision

Cap source files at **800 lines** and test files at **1000 lines**,
enforced via a Tier-2 ratchet keyed off ``.file-size-baseline.json``.

**Ratchet semantics:**
1. Files already over the limit when this ADR lands are recorded in
   ``.file-size-baseline.json`` at their current size. They may
   shrink (baseline auto-updates downward) but can never grow past
   the recorded baseline.
2. New files or files at or below the limit must stay at or below
   the limit. Crossing the threshold is a hard fail at pre-commit.
3. When a baselined file finally drops below its category limit, its
   entry is removed from the baseline file -- the standard limit
   takes over from there.

**Exceptions:**
Justified overages require:
1. A one-line comment near the top of the file naming the reason
   (e.g. ``# file-size: 1200 lines justified -- generated bindings``)
   AND
2. A line in ``.file-size-baseline.json`` recording the cap.

There is no project-wide override flag -- exceptions are
file-scoped and require human judgement at code review.

**Out of scope:**
- Bytecode size, function length, class length -- not enforced here.
- Generated ``.pyi`` / stub files under ``src/stubs/`` -- explicitly
  exempt.

## Consequences

**Immediate:**
- ``cli.py`` is grandfathered at 4478 lines and must shrink. A
  refactor sub-project will break it into ``cli/__init__.py`` +
  per-domain command modules (``cli/plugins.py``, ``cli/instance.py``,
  etc.). Tracked separately from this ADR.
- ``executor.py`` is grandfathered at 854 lines and may shrink to
  drop below the 800 cap, after which the baseline entry is
  removed.

**Going forward:**
- Every PR that grows a Python module pays a check at pre-commit.
- New helper modules are encouraged when a file approaches the cap;
  the convention is to extract pure helpers (no side effects) first
  and CLI / framework glue second.
- The ``file-headers`` rule and the file-size cap reinforce each
  other -- a file short enough to summarise in one line will rarely
  hit 800 lines.

**Tooling:**
- ``scripts/check_file_sizes.py`` walks ``src/nexus/`` and ``tests/``
  and emits violations.
- ``.pre-commit-config.yaml`` wires the script as a blocking gate.
- ``.claude/hooks/post-edit-lint.py`` also runs it for inline
  feedback during editing.
