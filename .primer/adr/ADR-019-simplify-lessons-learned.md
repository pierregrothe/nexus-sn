# ADR-019: Lessons from /simplify reviews

**Status:** accepted
**Date:** 2026-05-08
**Enforcement:** semgrep (3 new rules) + PR template + ADR commitment

## Context

Three /simplify sessions (PRs #2, #5, #6) caught real issues every time:

  - PR #2 (Agent SDK migration): efficiency findings (qualname recomputed
    per call, double-scan for unhashable args), code-quality findings
    (dead permissive_func parameter, stub docstrings).
  - PR #5 (cached decorator): style findings (over-engineered _Missing
    singleton, dead-code branches).
  - PR #6 (tier detection): the CRITICAL bug
    (KeychainClient(service_prefix="nexus") silently mismatched the
    Claude Code keychain key) plus an architectural limitation
    (@cached(persist=True) decoration-time backend capture broke test
    isolation, forcing a workaround).

The keychain bug almost shipped. Pre-commit hooks didn't catch it; tests
didn't catch it; only review caught it. The other findings are smaller
but recurring. Together they justify codifying the lessons.

## Decision

Bundle four threads into one PR:

1. **External-system credential reads** -- introduce
   ExternalKeychainClient(KeychainClient) thin subclass that calls
   super().__init__(service_prefix=""). Add Semgrep rule
   external-keychain-must-use-wrapper banning direct
   KeychainClient(service_prefix=...) usage in src/nexus/. Forces every
   call site to declare intent: KeychainClient() for NEXUS-owned secrets,
   ExternalKeychainClient() for other apps' secrets.

2. **@cached(persist=True) lazy-resolve.** Move
   _get_or_create_disk_backend(namespace) from decoration time into the
   wrapper. Tests can monkeypatch _disk_cache_root and clear
   _DISK_BACKENDS between tests; the next call picks up the new path.
   AgentClient adoption (deferred per ADR-017) is now unblocked.

3. **Three new Semgrep rules** for recurring style smells:
   external-keychain-must-use-wrapper, no-stub-see-docstring,
   enum-shadowing-label-dict (last one WARNING-only as heuristic). The
   "single-use module-private helper" pattern was considered but
   skipped -- Semgrep cannot detect it reliably.

4. **/simplify before merge as a process gate** via PR template
   checkbox. Solo-dev honor system, but the unchecked box is
   review-visible.

## Consequences

  - The keychain pattern bug class is closed. Adding a new external-app
    keychain reader requires using ExternalKeychainClient or fighting
    the Semgrep rule.
  - @cached(persist=True) is test-friendly. AgentClient.complete can
    adopt persist caching in a future PR without the disk-backend
    capture issue.
  - Three new lint rules. The enum-shadowing rule is heuristic
    (WARNING) and may produce false positives; refined pattern requires
    enum-style key (Enum.MEMBER) in the dict body, which excludes
    plain dict[str, str] / dict[int, str] usages.
  - PR template is a soft gate; it does not block merge. The value is
    in the conscious /simplify-or-skip choice it forces.
  - Adds nexus.auth.external_keychain module (~7 lines of code).

Spec: docs/superpowers/specs/2026-05-08-simplify-lessons-design.md
Plan: docs/superpowers/plans/2026-05-08-simplify-lessons.md
