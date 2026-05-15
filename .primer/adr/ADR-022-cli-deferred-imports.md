# ADR-022: Deferred imports inside Typer command bodies

**Status:** accepted
**Date:** 2026-05-14
**Enforcement:** soft (allowed in cli.py only; flagged elsewhere)

## Context

The pre-edit hook's Tier 1 `no-deferred-import` rule (see ADR-011) blocks function-body imports across the codebase to prevent module-load ordering bugs and to keep imports auditable at module top.

The CLI module (`src/nexus/cli.py`) breaks this rule deliberately. It has 15+ `# noqa: PLC0415` suppressions for lazy imports placed inside Typer command bodies. Typer commands are cold-boot performance-sensitive: every `nexus <subcommand>` invocation imports the entire CLI module to resolve which command to run, so importing heavy submodules (executor, AI agents, capture engine, knowledge subsystems) eagerly would penalize every CLI invocation -- including `nexus --help` and `nexus status`.

Subagents reviewing PRs in this area repeatedly flag the suppressions as in tension with the rule. Without an ADR, every reviewer rediscovers the rationale and the codebase looks inconsistent.

## Decision

`# noqa: PLC0415` is an **accepted, codified exception** when ALL of the following apply:

1. The import sits inside a Typer command body (`@app.command(...)` or `@subapp.command(...)` decorated function) in `src/nexus/cli.py`.
2. The imported module is large or has its own slow import (Anthropic SDK, executor, capture engine, AI subsystems).
3. The CLI entry point exists -- i.e. without the lazy import, `nexus --help` cold-start latency would degrade.

Deferred imports are NOT acceptable in:
- Library modules (`src/nexus/plugins/`, `src/nexus/connectors/`, etc.) -- module-top imports only.
- Test code -- always module-top.
- `cli.py` helper functions that aren't Typer command bodies.

The `# noqa: PLC0415` comment is required at the import line so a future reader sees the intentional suppression.

## Consequences

- Cold-start of `nexus --help` and other no-op invocations stays sub-second.
- The Tier 1 hook continues to fire elsewhere, catching accidental deferred imports in library code.
- Reviewers no longer need to relitigate the suppression on every CLI change; this ADR is the canonical answer.
- If the CLI grows enough that some subcommands become slow on their own, individual subcommands may warrant their own module (e.g. `src/nexus/cli/plugins.py`) to isolate cold-start cost.

## Migration

No code changes required. Existing `# noqa: PLC0415` suppressions in `cli.py` stand. Future CLI command bodies should follow the same pattern.

## Related

- ADR-011: 3-tier enforcement model (`no-deferred-import` rule)
- Pre-edit hook source: `.claude/hooks/pre-edit-validate.py`
- Reference site: `src/nexus/cli.py` (every `@app.command` / `@subapp.command` function body)
