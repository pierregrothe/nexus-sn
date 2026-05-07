# ADR-012: Dual Type Checking (mypy + pyright strict)

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** blocking (post-edit-lint.py) + CI

## Context

Sprint issue #4: _ModelsList Protocol was structurally incompatible with the SDK's
Models type. mypy passed because Anthropic uses Any for the models attribute. pyright
in strict mode would have caught the incompatibility via structural Protocol checking.
The two checkers complement each other -- mypy excels at control flow analysis,
pyright at structural compatibility and Protocol conformance.

## Decision

Both `mypy --strict` and `pyright --strict` must pass with 0 errors on every edited
Python file. The post-edit hook runs both. CI runs both. When they disagree, the
stricter interpretation wins. Fix the code, not the config.

mypy config: strict=true, warn_return_any=true, warn_unused_ignores=true,
strict_equality=true, python_version=3.14.

pyright config: typeCheckingMode=strict, pythonVersion=3.14.

## Consequences

_ModelDiscoveryClient now has a proper _ModelsList Protocol (list() -> Iterable[_ModelEntry])
that both mypy and pyright accept. cast() is used at SDK boundaries where structural
compatibility cannot be proven statically. No type: ignore is ever used.
