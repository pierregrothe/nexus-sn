# ADR-007: Zero type: ignore Tolerance

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** blocking hook (pre-edit-validate.py)

## Context

During MVP Step 1, four `# type: ignore[type-arg]` comments appeared in test fakes
to suppress list annotation errors. These masked real type gaps: fakes used
`SimpleNamespace` instead of typed dataclasses, and list return types were
unparameterized. The market-analysis-service blocks all type: ignore with the
same rationale.

## Decision

No `# type: ignore` comment is permitted anywhere in the codebase (src/ or tests/).
The pre-edit hook pattern `#\s*type:\s*ignore` blocks any file containing it.

For untyped third-party packages: add a stub file under `src/stubs/<package>.pyi`
or add `ignore_missing_imports = true` in `[mypy.<module>]` config for that package.

## Consequences

All existing type: ignore comments were removed in Plan 1. The pre-edit hook
enforces zero-tolerance going forward. Protocol definitions used in tests must be
structurally compatible with real objects -- no escaping via type: ignore.
