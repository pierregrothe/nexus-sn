# ADR-017: Single canonical caching decorator (@cached)

**Status:** accepted
**Date:** 2026-05-08
**Enforcement:** semgrep (3 rules) + Python TypeError + ValueError

## Context

NEXUS has four families of operations that benefit from caching: Agent SDK
LLM calls (persistent across runs), ServiceNow API responses (transient,
short TTL), capability probe results (semi-static, refresh every few
minutes), and config / paths / static lookups (infinite within a process).

Without a canonical decorator, each consumer would invent its own caching
layer with different semantics. Past projects accumulated a mix of
@functools.cache, @lru_cache(maxsize=...), @cached_property, manual
self._cache dicts, and ad-hoc TTL implementations. Replacing them is a
multi-PR migration; preventing them is a single decorator + a few rules.

## Decision

Introduce a Layer-0 utility `src/nexus/cache/` exporting `@cached(ttl, persist,
namespace, key_fn)` and `clear_cache(target)`. All caching in src/nexus/ uses
this decorator. Three Semgrep rules enforce it:

  - caching-must-use-cached-decorator -- blocks @cache, @lru_cache,
    @cached_property in src/nexus/
  - cached-requires-explicit-ttl -- @cached(...) without ttl= is rejected at
    Semgrep time; @cached() with no kwargs at all is rejected at decoration
    time by Python (TypeError, ttl is keyword-only with no default)
  - cached-persist-requires-namespace -- @cached(persist=True, ...) without
    namespace= is rejected at Semgrep time; the decorator factory also
    raises ValueError at decoration time

Backends:
  - InMemoryBackend (process-local dict, injectable clock for tests)
  - DiskBackend (wraps the diskcache library, sqlite-backed, persistent)

Per-instance scope: each cached method holds an _InstanceRegistry in its
closure. The registry uses WeakKeyDictionary by default; on TypeError
(@dataclass(slots=True, frozen=True) instances cannot be weakly referenced
because slots removes __weakref__) it falls back to a strong dict keyed by
id(instance). The fallback leaks until clear_cache() is called.

Free functions: backend is a module-level InMemoryBackend created once at
decoration time.

The decorator inspects parameter names via func.__code__.co_varnames rather
than inspect.signature() to avoid PEP 649 deferred-annotation evaluation,
which fails on forward references (e.g., NexusPaths.from_env -> NexusPaths
during class body construction).

## Consequences

  - One mental model for caching across the codebase.
  - One place to add observability (cache hit rate, eviction stats) when
    that becomes a need (deferred per spec).
  - Adds `diskcache >= 5.6` as a runtime dependency.
  - Instances cached by @cached must be hashable. Default for plain classes,
    frozen dataclasses, and frozen Pydantic models. Slots+frozen instances
    use the id-keyed fallback (memory leak until clear_cache()).
  - Function exceptions are NEVER cached; they are always re-raised.
  - Migration to actual cache adoption is staged: ConfigManager.load and
    NexusPaths.from_env land with this ADR. MCPProbe, ServiceNowClient,
    and AgentClient adopt later in their own PRs.

Spec: docs/superpowers/specs/2026-05-08-cached-decorator-design.md
Plan: docs/superpowers/plans/2026-05-08-cached-decorator.md
