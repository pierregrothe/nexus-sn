# ADR-011: 3-Tier Enforcement Model

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** governance doc + hook architecture

## Context

Sprint issues #12-13: the post-edit hook silently failed due to shell expansion.
The single-tier "block or ignore" model collapsed to "ignore" when the hook broke.
The market-analysis-service uses a 3-tier model (blocking, ratchet, soft) that
provides graduated enforcement.

## Decision

Three enforcement tiers:

Tier 1 -- Blocking (pre-edit-validate.py, PreToolUse): runs before file is written.
Failure prevents the write. Output on stderr. Zero tolerance.
Current rules (10): no-mocks, no-relative-imports, no-bare-except, no-lru-cache-none,
no-unittest-testcase, no-sys-argv, no-type-ignore, no-bare-any-in-sig,
no-dict-any-in-sig, no-deferred-import.

Tier 2 -- Ratchet (.ratchet.json, post-edit-lint.py): tracks numeric baselines.
Metrics can only improve. Currently tracks per-module covered lines.

Tier 3 -- Soft (post-edit-lint.py warning): advisory only. Currently tracks
missing-test-file and unclosed-resource-handle.

Hook reliability contract: REPO_ROOT via Path(__file__) (not shell expansion).
All blocking output on stderr. Exit codes: 0 clean, 2 blocking violation.

## Consequences

Broken hooks now produce stderr output visible in Claude Code blocking messages.
The hook command in settings.json uses relative paths (python3 .claude/hooks/...).
Pre-edit hook blocks 10 patterns at write time, not just at CI.
