# NEXUS Caching Decorator -- Design Spec

Date: 2026-05-08
Status: approved (brainstorming complete)
Author: Pierre Grothe

## Goal

Provide a single canonical `@cached` decorator for all caching needs in NEXUS,
governed by ADR-017 and enforced by Semgrep + runtime checks. Replaces ad-hoc
use of `functools.cache`, `functools.lru_cache`, and `functools.cached_property`.

## Why

Four use cases motivate the work:

1. Agent SDK call results (LLM responses) -- expensive, persistent across runs
2. ServiceNow API responses -- transient, short TTL within a session
3. MCP capability probe results -- semi-static, refresh every few minutes
4. Config / paths / static lookups -- infinite within a process

Without a single decorator, each consumer would invent its own caching layer
with different semantics. One decorator = one mental model + one place to
enforce governance rules.

## Architecture

### Module layout

```
src/nexus/cache/
  __init__.py     -- public exports: cached, clear_cache
  decorator.py    -- @cached implementation, async/sync auto-detect
  backends.py     -- CacheBackend Protocol + InMemoryBackend + DiskBackend
  keys.py         -- key generation: self handling, hashing, key_fn

tests/
  test_cache_decorator.py
  test_cache_backends.py
  test_cache_keys.py
  fakes/fake_cache_backend.py
  fakes/fake_clock.py
```

### Layer placement

`cache/` is a Layer 0 utility -- imports nothing from `nexus.*`, may be imported
by every other layer. Update `patterns.md` "Layer dependency rule":

```
cache -> (nothing in nexus)
config -> cache
auth -> config, cache
... (all other layers may import cache)
```

### Dependencies

- Add `diskcache >= 5.6` to `[tool.poetry.dependencies]` (runtime, not dev --
  production code uses it).
- Stdlib only otherwise: `functools.wraps`, `inspect.iscoroutinefunction`,
  `time.monotonic`, `hashlib`.

### Disk cache location

`~/.nexus/cache/<namespace>/` -- resolved via `NexusPaths`. Production code
passes `NexusPaths.from_env()`; tests pass `tmp_path`.

## API

### Signature

```python
def cached(
    *,
    ttl: int | None,                          # required keyword; seconds; None = infinite within process
    persist: bool = False,                    # True -> diskcache backend; requires namespace
    namespace: str | None = None,             # required when persist=True; key prefix on disk
    key_fn: Callable[..., str] | None = None, # custom key generator for non-hashable args
) -> Callable[[F], F]: ...
```

`ttl` has no default. `@cached()` raises `TypeError` at import time. This is
the runtime half of the "explicit TTL" governance rule (Semgrep is the static half).

### Companion API

```python
def clear_cache(target: Callable | object | None = None) -> None: ...
```

- `clear_cache(method)` -- clear one method's cache across all instances
- `clear_cache(instance)` -- clear all caches on a single instance
- `clear_cache()` -- clear all process-wide caches (testing only)

### Usage examples

```python
# Process-scoped, infinite (config / paths / static)
class ConfigManager:
    @cached(ttl=None)
    def read(self) -> NexusConfig: ...

# Process-scoped, TTL (capability probe)
class MCPProbe:
    @cached(ttl=300)
    async def _check_server(self, server: MCPServer) -> bool: ...

# Process-scoped, short TTL (ServiceNow API)
class ServiceNowClient:
    @cached(ttl=30)
    async def get_record(self, table: str, sys_id: str) -> dict[str, object]: ...

# Disk-persistent (Agent SDK)
class AgentClient:
    @cached(ttl=86400, persist=True, namespace="agent_sdk")
    async def complete(self, prompt: str, *, system: str | None = None,
                       model: str | None = None, max_turns: int = 1) -> str: ...

# Non-hashable arg (Pydantic model)
class TemplateRegistry:
    @cached(ttl=None, key_fn=lambda template: f"{template.name}:{template.version}")
    def resolve(self, template: TemplateModel) -> ResolvedTemplate: ...
```

### Behavior rules

- Async vs sync detected at decoration time via `inspect.iscoroutinefunction`.
- Disk caches survive across `nexus` invocations; in-memory caches die with
  the process.
- `persist=True` + `ttl=None` is allowed (cache forever on disk until cleared).
- Function exceptions are NEVER cached. They are re-raised, not stored.

## Cache key generation

Key format:

```
<namespace_prefix><module_qualname>:<arg_hash>
```

- `namespace_prefix` -- `"<namespace>:"` for `persist=True`, empty for in-memory
- `module_qualname` -- full dotted path: `"nexus.api.agent_client.AgentClient.complete"`
- `arg_hash` -- 16-hex-char SHA256 of `(repr(args), repr(sorted(kwargs.items())))`

Note: `self` is NOT in the key. Per-instance scope is provided by the
storage layout (see "Self handling" below), not by the key. Including
`id(self)` would be redundant for in-memory and unstable for disk.

### Hashability resolution order

1. If `key_fn` is provided, call it with `(*args, **kwargs)`. Use the returned
   string as `arg_hash`. Skip the rest.
2. Try `hash((args, tuple(sorted(kwargs.items()))))`. Use the result if it
   succeeds.
3. Try `repr()`-based hash. Stable for primitives, frozen dataclasses,
   Pydantic models with `frozen=True`. SHA256 the joined repr.
4. If none of the above work, raise `CacheKeyError` at first call (not
   decoration time -- the offending arg type may not be reachable in all paths).

### Self handling

- In-memory caches: `self` is the cache scope. Each `@cached`-decorated
  method holds a `WeakKeyDictionary[object, InMemoryBackend]` in its
  closure. The first call for an instance creates a backend and stores
  it in the dict; later calls reuse it. When the instance is garbage
  collected, the weak reference clears and the backend is freed.
  Constraint: the instance must be hashable (`@dataclass(frozen=True)`,
  Pydantic `frozen=True`, and plain classes all are by default).
  Unhashable instances raise `TypeError` from the WeakKeyDictionary
  insert at first call.
  This pattern works for `@dataclass(slots=True, frozen=True)` types
  like `NexusPaths` where attribute storage on the instance is impossible.
- Free functions: backend is a module-level `InMemoryBackend` created
  once at decoration time. No instance scope.
- Class methods (`cls` as first arg): same WeakKeyDictionary pattern;
  `cls` is the key. All instances of the class share one cache (since
  `cls` is the same object).
- Disk caches: `self` is excluded from the key. `namespace` is the only
  separator. Per-instance disk caching requires a dynamic `namespace`
  (e.g., `namespace=f"sn:{instance_label}"`).

## Governance

### ADR-017: Single canonical caching decorator

Document the design and the three enforcement rules. Link to this spec.

### Enforcement matrix

| Rule | Mechanism | Where |
|---|---|---|
| All caching uses `@cached` | Semgrep | `.semgrep/rules.yml` |
| `ttl=` is required | Python `TypeError` + Semgrep | runtime + `.semgrep/rules.yml` |
| `namespace=` required when `persist=True` | Python `ValueError` + Semgrep | decoration time + `.semgrep/rules.yml` |
| Non-hashable args declared via `key_fn` | Runtime `CacheKeyError` | first call only |

The dual-enforcement (runtime + Semgrep) for `ttl` and `namespace` is intentional:
runtime gives a clear error if someone bypasses lint via dynamic decoration;
Semgrep gives editor-time feedback before tests run. Both messages reference
ADR-017.

### Concrete Semgrep rule names

- `caching-must-use-cached-decorator` -- blocks `@cache`, `@functools.cache`,
  `@cached_property`, `@lru_cache(...)` in `src/nexus/`. Tests are exempt.
- `cached-requires-explicit-ttl` -- blocks `@cached(persist=...)` without `ttl=`.
- `cached-persist-requires-namespace` -- blocks `@cached(persist=True, ...)`
  without `namespace=`.

The existing `no-lru-cache-none` rule from ADR-016 stays. It is a strict
subset, but its specific message is more useful than the generic "use @cached"
when someone writes `@lru_cache(maxsize=None)`.

### governance.md update

Add a new line under "Tier 1 -- Blocking (semgrep)":

```
- caching-must-use-cached-decorator -- @cache, @lru_cache, @cached_property
  forbidden in src/nexus/ (ADR-017)
- cached-requires-explicit-ttl -- @cached without ttl= is forbidden (ADR-017)
- cached-persist-requires-namespace -- @cached(persist=True) without namespace=
  is forbidden (ADR-017)
```

## Testing

### Test files

```
tests/test_cache_decorator.py    -- @cached behavior: hit, miss, async, sync,
                                    exceptions, scope, key_fn override
tests/test_cache_backends.py     -- InMemoryBackend + DiskBackend in isolation
tests/test_cache_keys.py         -- key generation: hashable / non-hashable,
                                    key_fn, self handling
tests/fakes/fake_cache_backend.py -- for tests of consumers
tests/fakes/fake_clock.py         -- deterministic time for TTL tests
```

### Deterministic time

`InMemoryBackend.__init__(self, *, clock: Callable[[], float] = time.monotonic)`.
Tests inject a `FakeClock` (real Python class with `now()` and `advance(seconds)`):

```python
def test_cached_returns_stale_until_ttl_expires() -> None:
    clock = FakeClock(start=1000.0)
    backend = InMemoryBackend(clock=clock.now)
    backend.set("key", "value", ttl=60)
    clock.advance(60)
    assert backend.get("key") == "value"
    clock.advance(1)
    assert backend.get("key") is None
```

### Disk cache isolation

`DiskBackend.__init__(self, *, cache_dir: Path)`. Tests pass `tmp_path / "cache"`.
The `@cached` wrapper resolves `cache_dir` from `NexusPaths` only at the
production entry point.

### Per-instance scope test

```python
def test_cached_scope_is_per_instance() -> None:
    a = ConfigManager(...)
    b = ConfigManager(...)
    a.read()
    b.read()
    # underlying load called twice; each instance has its own cache
```

### FakeCacheBackend for downstream consumers

Records every `get` / `set` / `delete` call. Returns the most recent `set`
value. Used when testing `ConfigManager`, `MCPProbe`, etc. -- those tests
verify "the method was decorated and the cache layer is invoked" without
exercising real backends.

### Coverage target

100% on `nexus.cache.*` per existing project gate. ~25-30 tests across the
3 test files.

### Out of test scope

- No DiskBackend integration test against real `~/.nexus/cache/` -- purely
  `tmp_path`. End-to-end signal comes from the Agent SDK smoke script if
  `AgentClient.complete` adopts `@cached(persist=True)` later.

## Migration plan

### Initial PR (this spec)

Produces the cache module + governance + adoption in two consumers end-to-end:

- `ConfigManager.read()` -- pure sync, `ttl=None`, currently does a real
  disk read every call. Adoption is observable (cache hit on second call)
  and risk-free (config reads are not a hot path).
- `NexusPaths.from_env()` -- classmethod, no args, `ttl=None`. Trivial
  (~3 lines), free win.

### Deferred to follow-up PRs

| Target | Trigger | Notes |
|---|---|---|
| `MCPProbe._check_server()` | When probe is implemented (currently a `False` stub) | `@cached(ttl=300)` |
| `ServiceNowClient.get_record()` | When CLI commands exercise it | `@cached(ttl=30)`; existing `dict[str, Any]` arg type still grandfathered |
| `AgentClient.complete()` | After first stable PyPI release | `@cached(ttl=86400, persist=True, namespace="agent_sdk")`; LLM result caching is the highest-value but most failure-prone case -- wait until other surfaces have shaken out |

The cache module supports all four cases from day 1. Adoption is staged to
keep each PR small and reviewable.

### Coverage ratchet

`.ratchet.json` gains four entries: `nexus.cache.decorator`,
`nexus.cache.backends`, `nexus.cache.keys`, `nexus.cache.__init__`.
`nexus.config.manager` baseline bumps slightly from the new cache adoption test.

### Rollback

If a `@cached`-decorated method shows unexpected staleness, the fix is one
line: `@cached(ttl=None)` -> `@cached(ttl=5)` or removal of the decorator.
No deeper unwinding.

## Out of scope (future work)

- Cache stats / observability (`@cached.stats()` for hit rate)
- Cross-process invalidation -- diskcache handles concurrency at the storage
  layer; revisit if multi-process workflows emerge
- Cache versioning on SDK upgrade -- when `claude-agent-sdk` bumps major
  version, persisted Agent SDK results may be invalidly formatted. Punt:
  namespace includes SDK version (caller's responsibility, documented in ADR-017)
- Decorator stacking with `@property`, `@classmethod` -- not part of v1
  use cases; document as unsupported; revisit on demand
