# ADR-016: Semgrep for semantic governance rules

**Status:** accepted
**Date:** 2026-05-08
**Enforcement:** semgrep (pre-commit + CI lint stage)

## Context

The custom pre-edit hook (.claude/hooks/pre-edit-validate.py) had grown to
10 regex-based checks. Five of them duplicated rules already configurable
in ruff:

  - no-mocks (ruff banned-api -- already configured)
  - no-relative-imports (ruff ban-relative-imports -- already configured)
  - no-bare-except (ruff E722 -- already in default select)
  - no-deferred-import (ruff PLC0415 -- not yet selected)
  - no-type-ignore (ruff PGH003 -- not yet selected)

Three more rules expressed semantic patterns ruff cannot match cleanly:

  - no-lru-cache(maxsize=None): decorator pattern
  - no-unittest.TestCase in test files: subclass detection
  - no-dict-any-in-sig: typed-signature pattern (false-positive prone in ruff)

The remaining two checks are file-aware and stay in the custom hook:

  - no-sys-argv (allowed in tests/, blocked in src/)
  - no-bare-any-in-sig (ruff ANN401 is too broad; legitimate Any usage in
    Protocol return types must be permitted outside signatures)

## Decision

Adopt Semgrep for the semantic governance bucket. Keep ruff as the
syntactic-rules bucket. Keep the custom Python pre-edit hook for the
file-aware bucket. Each rule has exactly one home:

  - Ruff (syntactic, expressible via lint config): no-mocks,
    no-relative-imports, no-bare-except, no-deferred-import (PLC0415),
    no-type-ignore (PGH003)
  - Semgrep (semantic patterns, .semgrep/rules.yml): no-lru-cache-none,
    no-unittest-testcase. Future: ServiceNowClient import boundaries,
    Pydantic ConfigDict invariants, datetime UTC enforcement.
  - Custom Python hook (file-aware, .claude/hooks/pre-edit-validate.py):
    no-sys-argv, no-bare-any-in-sig, no-dict-any-in-sig

Semgrep is installed via pre-commit's per-hook isolated venv
(additional_dependencies in .pre-commit-config.yaml), not via Poetry.
This keeps semgrep's 50+ transitive deps (opentelemetry, mcp, ruamel-yaml,
etc.) out of the project lockfile and avoids the typer/click downgrade
poetry would otherwise force.

## Consequences

  - One source of truth per rule. Less duplication, less regex churn.
  - Semgrep rules carry an `metadata.adr` field linking each rule to its
    governing ADR -- traceable enforcement.
  - Semgrep adds ~5-10s to pre-commit on a clean repo (one-time cost when
    the isolated venv is built; cached afterwards).
  - The custom hook shrinks from 10 checks to 3, easier to audit.
  - Ruff config grows by 2 selected rule families (PGH, PLC0415).
  - New governance rules are now cheaper to add: write a Semgrep YAML
    pattern instead of a Python regex with manual scope handling.
