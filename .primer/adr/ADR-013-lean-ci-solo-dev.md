# ADR-013: Lean CI for Solo Developer

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** ci.yml

## Context

The original CI ran the full test suite on a 3-OS matrix (ubuntu/macos/windows) on
every push. For a solo developer who tests locally before every commit, this was
redundant overhead (3+ minutes) that slowed feedback without adding safety.

## Decision

CI is restructured into two stages:

Stage 1 -- Lint/type (every push, <30 seconds):
- black --check, ruff check, mypy, pyright
- Single OS (ubuntu-latest), single Python (3.14), no matrix.

Stage 2 -- Full tests (release tags only):
- pytest --cov-fail-under=100
- Cross-platform matrix: ubuntu + macos + windows

Local enforcement: pre-commit hook runs pytest before every commit.
Post-edit hook enforces per-module coverage ratchet after every file write.

## Consequences

CI feedback is fast (<30s) for every push. Test coverage is enforced locally via
post-edit hook and pre-commit hook. If a co-developer joins, Stage 2 should be
moved back to every push. The pyrightconfig.json `pythonPlatform: "Darwin"` should
be changed to null or removed for CI (Linux runner) compatibility.
