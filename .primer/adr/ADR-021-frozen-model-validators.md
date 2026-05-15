# ADR-021: Coherent construction on frozen Pydantic models

**Status:** accepted
**Date:** 2026-05-14
**Enforcement:** agent (preferred pattern; no hook)

## Context

NEXUS uses Pydantic v2 frozen+strict+extra=forbid models throughout (per ADR-007 and CLAUDE.md conventions). Aggregate result models commonly carry derived fields -- counts, totals, success ratios -- alongside the raw collection they summarize. Two patterns are available:

1. `@computed_field` + `@property` -- the Pydantic-idiomatic way to expose derived values that participate in `model_dump()` serialization.
2. Stored fields + `@model_validator(mode="after")` -- store the derived values as explicit fields, enforce consistency at construction time.

The first attempt at `BatchUpgradeReport` used pattern 1. mypy strict mode rejected it with `error: Decorators on top of @property are not supported  [prop-decorator]`. This is a known mypy limitation; the `pydantic.mypy` plugin does **not** suppress it, and `# type: ignore` is forbidden by ADR-007.

## Decision

For frozen Pydantic models that carry derived values needed in `model_dump()` output, use **pattern 2**: stored fields plus an after-validator that enforces coherence.

Reference shape (from `nexus.plugins.executor.BatchUpgradeReport`):

```python
class BatchUpgradeReport(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    results: tuple[OperationResult, ...]
    target_count: int
    succeeded: int
    failed: int

    @model_validator(mode="after")
    def _check_counts_coherent(self) -> Self:
        if self.target_count != len(self.results):
            raise ValueError(
                f"target_count ({self.target_count}) != len(results) ({len(self.results)})"
            )
        actual_succeeded = sum(1 for r in self.results if r.success)
        if self.succeeded != actual_succeeded:
            raise ValueError(f"succeeded ({self.succeeded}) != actual ({actual_succeeded})")
        if self.succeeded + self.failed != self.target_count:
            raise ValueError(
                f"succeeded + failed ({self.succeeded + self.failed}) "
                f"!= target_count ({self.target_count})"
            )
        return self
```

When derived values are NOT needed in `model_dump()` -- i.e. they are only used by Python callers -- plain `@property` is fine (no `@computed_field` wrapper, no decorator stacking). The existing `OperationLog.success_count` / `failure_count` properties are the canonical example.

## Consequences

- mypy strict stays clean without `# type: ignore`.
- Constructors enforce coherence at validation time -- callers cannot build a report with inconsistent counts (e.g. `target_count=5` and `results=()`).
- One extra O(N) recompute happens at construction (the validator re-derives counts to verify). For batch sizes this layer handles (~hundreds of plugins / operations), the cost is negligible.
- Error messages use a consistent parenthesised form: `"x (123) != y (456)"`.
- `model_dump()` includes the stored fields naturally -- no `@computed_field` plumbing.

## Related

- ADR-007: Zero `# type: ignore`
- ADR-012: Dual type checking (mypy + pyright strict)
- Reference implementation: `src/nexus/plugins/executor.py:BatchUpgradeReport`
