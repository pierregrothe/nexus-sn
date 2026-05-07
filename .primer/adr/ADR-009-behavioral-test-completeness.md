# ADR-009: Behavioral Test Completeness

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** ratchet (.ratchet.json, post-edit hook)

## Context

Sprint issue #7: the configure_logging test only verified directory creation, not
that handlers were attached. The test passed even when the handler-attachment code
was unreachable (due to conftest.py setting up root logger at module scope). Issue
#8: filter exclusion logic in _discover_model had no tests at all.

## Decision

Three rules:

1. Every code path must be exercised. Per-module coverage is tracked in .ratchet.json.
   The post-edit hook runs pytest for the edited module and blocks if covered lines
   decrease from baseline.

2. Tests must assert on behavior. A test whose assertions could all pass even if the
   function raised NotImplementedError is a vacuous test. Tests must assert on return
   values, state changes, or side effects of the function being tested.

3. Coverage gate is 100% (pyproject.toml --cov-fail-under=100). Stub modules are
   excluded from the ratchet baseline until they have implementations.

## Consequences

Logging tests must clear root logger handlers before testing, then restore them in
a finally block with explicit handler.close() calls. Filter/exclusion logic requires
dedicated tests for each filtering rule. The ratchet baseline in .ratchet.json stores
per-module covered-lines counts.
