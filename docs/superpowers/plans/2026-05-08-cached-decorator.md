# Cached Decorator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a single canonical `@cached` decorator (sync + async) backed by in-memory and disk caches, with three Semgrep enforcement rules and ADR-017 governance, and adopt it on `ConfigManager.read()` and `NexusPaths.from_env()`.

**Architecture:** Layer-0 utility package `src/nexus/cache/` with separate modules for keys, backends, and the decorator. Per-instance scope via a `WeakKeyDictionary` in the decorator closure (works for frozen+slots dataclasses). Disk persistence via `diskcache` library.

**Tech Stack:** Python 3.14, `diskcache >= 5.6` (new runtime dep), `weakref.WeakKeyDictionary`, `inspect.iscoroutinefunction`, `hashlib.sha256`, semgrep for governance.

---

## File Map

```
ADD:
  src/nexus/cache/__init__.py           -- exports cached, clear_cache, CacheKeyError
  src/nexus/cache/errors.py             -- CacheKeyError exception
  src/nexus/cache/keys.py               -- compute_key, _MISSING sentinel
  src/nexus/cache/backends.py           -- CacheBackend Protocol, InMemoryBackend, DiskBackend
  src/nexus/cache/decorator.py          -- @cached, clear_cache
  tests/test_cache_keys.py              -- key generation tests
  tests/test_cache_backends.py          -- backend tests
  tests/test_cache_decorator.py         -- decorator tests
  tests/fakes/fake_clock.py             -- deterministic clock for TTL tests
  tests/fakes/fake_cache_backend.py     -- backend fake for consumer tests
  .primer/adr/ADR-017-canonical-caching-decorator.md

MODIFY:
  pyproject.toml                        -- add diskcache >= 5.6 to runtime deps
  tests/fakes/__init__.py               -- export FakeClock + FakeCacheBackend
  .semgrep/rules.yml                    -- add 3 rules (caching-must-use-cached-decorator,
                                           cached-requires-explicit-ttl,
                                           cached-persist-requires-namespace)
  src/nexus/config/manager.py           -- adopt @cached(ttl=None) on read()
  src/nexus/config/paths.py             -- adopt @cached(ttl=None) on from_env()
  tests/test_config.py                  -- add cache-hit assertion test
  .ratchet.json                         -- add 5 new modules + bump config.manager
  .primer/governance.md                 -- 3 new gates, add ADR-017 to catalog
  .primer/patterns.md                   -- layer 0 entry in dependency rule
  .primer/decisions.md                  -- append ADR-017 entry
```

---

## Task 1: Add diskcache dep + create errors module

**Files:**
- Modify: `pyproject.toml`
- Create: `src/nexus/cache/__init__.py` (placeholder)
- Create: `src/nexus/cache/errors.py`

- [ ] **Step 1: Add diskcache to pyproject.toml**

In `[tool.poetry.dependencies]`, add after `keyring`:

```toml
diskcache = ">=5.6"
```

- [ ] **Step 2: Install via Poetry**

```bash
cd /Users/pierre.grothe/Developer/nexus && poetry lock && poetry install
```

Expected: `diskcache` installed; `poetry.lock` updated.

- [ ] **Step 3: Create the cache package skeleton**

Write `src/nexus/cache/__init__.py`:

```python
# src/nexus/cache/__init__.py
# Layer-0 caching utility -- exports the @cached decorator, clear_cache, and CacheKeyError.
# Author: Pierre Grothe
# Date: 2026-05-08
"""NEXUS canonical caching decorator (ADR-017).

All caching in src/nexus/ goes through @cached. Direct use of functools.cache,
functools.lru_cache, and functools.cached_property is forbidden by Semgrep.
"""

from nexus.cache.errors import CacheKeyError

__all__ = ["CacheKeyError"]
```

(`cached` and `clear_cache` are added to `__all__` in Task 4 once they exist.)

- [ ] **Step 4: Create errors.py**

Write `src/nexus/cache/errors.py`:

```python
# src/nexus/cache/errors.py
# Exceptions raised by the cache decorator.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Cache-layer exception types."""

__all__ = ["CacheKeyError"]


class CacheKeyError(Exception):
    """Raised when a @cached method receives an arg whose type is not hashable.

    The decorator cannot generate a stable cache key for this call. Declare
    a custom ``key_fn`` on the @cached decorator to convert the arg to a
    hashable string. See ADR-017.
    """
```

- [ ] **Step 5: Verify the package imports**

```bash
.venv/bin/python -c "from nexus.cache import CacheKeyError; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml poetry.lock src/nexus/cache/__init__.py src/nexus/cache/errors.py && git commit -m "feat(cache): add diskcache dep and CacheKeyError skeleton"
```

---

## Task 2: Implement keys.py (cache key generation)

**Files:**
- Create: `src/nexus/cache/keys.py`
- Create: `tests/test_cache_keys.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cache_keys.py`:

```python
# tests/test_cache_keys.py
# Tests for nexus.cache.keys.compute_key.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for cache key generation."""

from dataclasses import dataclass

import pytest

from nexus.cache.errors import CacheKeyError
from nexus.cache.keys import compute_key


def _func() -> None:
    """Sample function used to derive module_qualname in keys."""


def test_compute_key_includes_module_qualname() -> None:
    key = compute_key(_func, args=(), kwargs={}, namespace=None, key_fn=None)
    assert "tests.test_cache_keys._func" in key


def test_compute_key_with_primitive_args_is_deterministic() -> None:
    k1 = compute_key(_func, args=(1, "x"), kwargs={}, namespace=None, key_fn=None)
    k2 = compute_key(_func, args=(1, "x"), kwargs={}, namespace=None, key_fn=None)
    assert k1 == k2


def test_compute_key_with_different_args_produces_different_keys() -> None:
    k1 = compute_key(_func, args=(1,), kwargs={}, namespace=None, key_fn=None)
    k2 = compute_key(_func, args=(2,), kwargs={}, namespace=None, key_fn=None)
    assert k1 != k2


def test_compute_key_sorts_kwargs_for_determinism() -> None:
    k1 = compute_key(_func, args=(), kwargs={"a": 1, "b": 2}, namespace=None, key_fn=None)
    k2 = compute_key(_func, args=(), kwargs={"b": 2, "a": 1}, namespace=None, key_fn=None)
    assert k1 == k2


def test_compute_key_with_namespace_prefix() -> None:
    key = compute_key(_func, args=(), kwargs={}, namespace="agent_sdk", key_fn=None)
    assert key.startswith("agent_sdk:")


def test_compute_key_with_no_namespace_has_no_prefix() -> None:
    key = compute_key(_func, args=(), kwargs={}, namespace=None, key_fn=None)
    assert not key.startswith(":")
    assert "tests.test_cache_keys._func" in key


def test_compute_key_uses_key_fn_when_provided() -> None:
    key = compute_key(
        _func,
        args=(42,),
        kwargs={},
        namespace=None,
        key_fn=lambda x: f"custom:{x}",
    )
    assert "custom:42" in key


@dataclass(frozen=True)
class _FrozenSample:
    name: str
    value: int


def test_compute_key_with_frozen_dataclass_arg_uses_repr() -> None:
    sample = _FrozenSample(name="x", value=1)
    k1 = compute_key(_func, args=(sample,), kwargs={}, namespace=None, key_fn=None)
    k2 = compute_key(_func, args=(sample,), kwargs={}, namespace=None, key_fn=None)
    assert k1 == k2


def test_compute_key_with_unhashable_arg_raises_cache_key_error() -> None:
    unhashable = {"dict": "not hashable"}
    with pytest.raises(CacheKeyError, match="dict"):
        compute_key(_func, args=(unhashable,), kwargs={}, namespace=None, key_fn=None)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_cache_keys.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.cache.keys`.

- [ ] **Step 3: Implement keys.py**

Write `src/nexus/cache/keys.py`:

```python
# src/nexus/cache/keys.py
# Cache key generation for the @cached decorator.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Compute deterministic cache keys for the @cached decorator (ADR-017)."""

import hashlib
from collections.abc import Callable
from typing import Any

from nexus.cache.errors import CacheKeyError

__all__ = ["compute_key"]

_HASH_LEN = 16


def compute_key(
    func: Callable[..., Any],
    *,
    args: tuple[object, ...],
    kwargs: dict[str, object],
    namespace: str | None,
    key_fn: Callable[..., str] | None,
) -> str:
    """Build a deterministic cache key for a function call.

    Format: "[namespace:]<module.qualname>:<arg_hash>"

    Args:
        func: The cached function (used for module + qualname).
        args: Positional args passed to the call.
        kwargs: Keyword args passed to the call.
        namespace: Optional prefix for disk caches.
        key_fn: Optional custom key generator. When provided, replaces the
            default hashing of args + kwargs.

    Returns:
        A stable string key.

    Raises:
        CacheKeyError: When an arg is not hashable and no key_fn is given.
    """
    qualname = f"{func.__module__}.{func.__qualname__}"
    if key_fn is not None:
        arg_hash = key_fn(*args, **kwargs)
    else:
        arg_hash = _hash_call_args(args, kwargs)
    prefix = f"{namespace}:" if namespace else ""
    return f"{prefix}{qualname}:{arg_hash}"


def _hash_call_args(args: tuple[object, ...], kwargs: dict[str, object]) -> str:
    """Return a stable hash for (args, sorted_kwargs).

    Tries hash() first (cheap path), falls back to repr-based SHA256 for
    types that aren't hashable but have a stable repr (Pydantic frozen
    models, frozen dataclasses, etc.).
    """
    sorted_kwargs = tuple(sorted(kwargs.items()))
    try:
        hashed = hash((args, sorted_kwargs))
    except TypeError:
        return _repr_sha256(args, sorted_kwargs)
    return f"h{hashed:x}"


def _repr_sha256(args: tuple[object, ...], sorted_kwargs: tuple[tuple[str, object], ...]) -> str:
    """SHA256 over repr(args) + repr(sorted_kwargs). Used when hash() fails.

    Raises:
        CacheKeyError: If any arg has no stable repr (rare; mostly for dict/list/set).
    """
    try:
        payload = repr(args) + "|" + repr(sorted_kwargs)
    except Exception as exc:
        raise CacheKeyError(f"could not produce stable repr for args: {exc}") from exc
    if any(_is_known_unhashable(a) for a in args):
        offending = next(type(a).__name__ for a in args if _is_known_unhashable(a))
        raise CacheKeyError(
            f"@cached received unhashable arg of type {offending!r}; "
            "declare key_fn=lambda ... on the decorator (ADR-017)."
        )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest[:_HASH_LEN]


def _is_known_unhashable(obj: object) -> bool:
    """Return True for dict/list/set -- mutable containers we refuse to hash."""
    return isinstance(obj, (dict, list, set))
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_cache_keys.py -v --override-ini="addopts="
```

Expected: 9 passed.

- [ ] **Step 5: Lint + type-check**

```bash
.venv/bin/ruff check src/nexus/cache/keys.py tests/test_cache_keys.py
.venv/bin/mypy src/nexus/cache/keys.py
.venv/bin/pyright src/nexus/cache/keys.py tests/test_cache_keys.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 6: Commit**

```bash
git add src/nexus/cache/keys.py tests/test_cache_keys.py && git commit -m "feat(cache): compute_key for cache key generation"
```

---

## Task 3: Implement backends.py + FakeClock

**Files:**
- Create: `src/nexus/cache/backends.py`
- Create: `tests/fakes/fake_clock.py`
- Modify: `tests/fakes/__init__.py`
- Create: `tests/test_cache_backends.py`

- [ ] **Step 1: Create FakeClock**

Write `tests/fakes/fake_clock.py`:

```python
# tests/fakes/fake_clock.py
# Deterministic clock for TTL tests -- no time.monotonic, no mocks.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeClock: a controllable monotonic clock for tests."""

from dataclasses import dataclass

__all__ = ["FakeClock"]


@dataclass(slots=True)
class FakeClock:
    """A deterministic clock for tests.

    Use ``now()`` where production code calls ``time.monotonic()``.
    Use ``advance(seconds)`` to move time forward.

    Attributes:
        current: The current time (float seconds, monotonic-style).
    """

    current: float = 0.0

    def now(self) -> float:
        """Return the current monotonic-style time."""
        return self.current

    def advance(self, seconds: float) -> None:
        """Move the clock forward by ``seconds``."""
        self.current += seconds
```

- [ ] **Step 2: Update tests/fakes/__init__.py**

Read the current file. Add FakeClock import + __all__ entry:

```python
# tests/fakes/__init__.py
# Fake implementations used in tests. No mocks anywhere.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Fake connectors and clients for use in tests."""

from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__ = [
    "FakeAgentClient",
    "FakeClock",
    "FakeKeychainClient",
    "FakeServiceNowClient",
]
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_cache_backends.py`:

```python
# tests/test_cache_backends.py
# Tests for nexus.cache.backends.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for InMemoryBackend and DiskBackend."""

from pathlib import Path

from nexus.cache.backends import MISSING, DiskBackend, InMemoryBackend
from tests.fakes.fake_clock import FakeClock


def test_in_memory_backend_get_returns_missing_when_empty() -> None:
    backend = InMemoryBackend(clock=FakeClock().now)
    assert backend.get("key") is MISSING


def test_in_memory_backend_set_then_get_returns_value() -> None:
    backend = InMemoryBackend(clock=FakeClock().now)
    backend.set("key", "value", ttl=None)
    assert backend.get("key") == "value"


def test_in_memory_backend_returns_value_within_ttl() -> None:
    clock = FakeClock(current=1000.0)
    backend = InMemoryBackend(clock=clock.now)
    backend.set("key", "v", ttl=60)
    clock.advance(59)
    assert backend.get("key") == "v"


def test_in_memory_backend_returns_missing_after_ttl_expires() -> None:
    clock = FakeClock(current=1000.0)
    backend = InMemoryBackend(clock=clock.now)
    backend.set("key", "v", ttl=60)
    clock.advance(61)
    assert backend.get("key") is MISSING


def test_in_memory_backend_caches_none_distinct_from_missing() -> None:
    backend = InMemoryBackend(clock=FakeClock().now)
    backend.set("key", None, ttl=None)
    assert backend.get("key") is None
    assert backend.get("key") is not MISSING


def test_in_memory_backend_delete_removes_value() -> None:
    backend = InMemoryBackend(clock=FakeClock().now)
    backend.set("key", "v", ttl=None)
    backend.delete("key")
    assert backend.get("key") is MISSING


def test_in_memory_backend_clear_removes_all_values() -> None:
    backend = InMemoryBackend(clock=FakeClock().now)
    backend.set("a", 1, ttl=None)
    backend.set("b", 2, ttl=None)
    backend.clear()
    assert backend.get("a") is MISSING
    assert backend.get("b") is MISSING


def test_disk_backend_set_then_get_returns_value(tmp_path: Path) -> None:
    backend = DiskBackend(cache_dir=tmp_path)
    backend.set("key", "value", ttl=None)
    assert backend.get("key") == "value"


def test_disk_backend_get_returns_missing_when_absent(tmp_path: Path) -> None:
    backend = DiskBackend(cache_dir=tmp_path)
    assert backend.get("key") is MISSING


def test_disk_backend_persists_across_instances(tmp_path: Path) -> None:
    a = DiskBackend(cache_dir=tmp_path)
    a.set("key", "persisted", ttl=None)
    b = DiskBackend(cache_dir=tmp_path)
    assert b.get("key") == "persisted"


def test_disk_backend_delete_removes_value(tmp_path: Path) -> None:
    backend = DiskBackend(cache_dir=tmp_path)
    backend.set("key", "v", ttl=None)
    backend.delete("key")
    assert backend.get("key") is MISSING


def test_disk_backend_clear_removes_all_values(tmp_path: Path) -> None:
    backend = DiskBackend(cache_dir=tmp_path)
    backend.set("a", 1, ttl=None)
    backend.set("b", 2, ttl=None)
    backend.clear()
    assert backend.get("a") is MISSING
    assert backend.get("b") is MISSING
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_cache_backends.py -v --override-ini="addopts="
```

Expected: ImportError on `nexus.cache.backends`.

- [ ] **Step 5: Implement backends.py**

Write `src/nexus/cache/backends.py`:

```python
# src/nexus/cache/backends.py
# Cache backend Protocol + InMemoryBackend + DiskBackend.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Cache backends used by @cached.

InMemoryBackend lives in process; DiskBackend wraps the diskcache library
and persists across runs. Both implement CacheBackend Protocol.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import diskcache

__all__ = ["MISSING", "CacheBackend", "DiskBackend", "InMemoryBackend"]


class _Missing:
    """Sentinel singleton for "no cached value" -- distinct from None."""

    _instance: "_Missing | None" = None

    def __new__(cls) -> "_Missing":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "<MISSING>"


MISSING = _Missing()


class CacheBackend(Protocol):
    """Sync cache backend interface."""

    def get(self, key: str) -> object:
        """Return the cached value or MISSING if absent or expired."""

    def set(self, key: str, value: object, ttl: int | None) -> None:
        """Store ``value`` under ``key`` with ``ttl`` seconds. None = no expiry."""

    def delete(self, key: str) -> None:
        """Remove ``key`` from the cache. No-op if absent."""

    def clear(self) -> None:
        """Remove all entries from the cache."""


@dataclass(slots=True)
class _Entry:
    """Internal entry: cached value + monotonic-time expiry. None = no expiry."""

    value: object
    expires_at: float | None


@dataclass(slots=True)
class InMemoryBackend:
    """Process-local cache. Backed by a dict, expiry checked on every get.

    Args:
        clock: Callable returning monotonic-style float seconds. Defaults to
            ``time.monotonic``. Tests inject a FakeClock.
    """

    clock: Callable[[], float] = field(default=time.monotonic)
    _store: dict[str, _Entry] = field(default_factory=dict)

    def get(self, key: str) -> object:
        """See CacheBackend.get."""
        entry = self._store.get(key)
        if entry is None:
            return MISSING
        if entry.expires_at is not None and self.clock() >= entry.expires_at:
            del self._store[key]
            return MISSING
        return entry.value

    def set(self, key: str, value: object, ttl: int | None) -> None:
        """See CacheBackend.set."""
        expires_at = None if ttl is None else self.clock() + ttl
        self._store[key] = _Entry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> None:
        """See CacheBackend.delete."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """See CacheBackend.clear."""
        self._store.clear()


class DiskBackend:
    """Persistent cache backed by the diskcache library.

    Args:
        cache_dir: Directory for the sqlite-backed store. Created if absent.
    """

    def __init__(self, *, cache_dir: Path) -> None:
        """Open the diskcache at ``cache_dir``."""
        self._cache = diskcache.Cache(directory=str(cache_dir))

    def get(self, key: str) -> object:
        """See CacheBackend.get."""
        result = self._cache.get(key, default=MISSING)
        return result

    def set(self, key: str, value: object, ttl: int | None) -> None:
        """See CacheBackend.set."""
        self._cache.set(key, value, expire=ttl)

    def delete(self, key: str) -> None:
        """See CacheBackend.delete."""
        self._cache.delete(key)

    def clear(self) -> None:
        """See CacheBackend.clear."""
        self._cache.clear()
```

- [ ] **Step 6: Run tests**

```bash
.venv/bin/pytest tests/test_cache_backends.py -v --override-ini="addopts="
```

Expected: 12 passed.

- [ ] **Step 7: Lint + type-check**

```bash
.venv/bin/ruff check src/nexus/cache/backends.py tests/fakes/fake_clock.py tests/test_cache_backends.py
.venv/bin/mypy src/nexus/cache/backends.py
.venv/bin/pyright src/nexus/cache/backends.py tests/fakes/fake_clock.py tests/test_cache_backends.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 8: Commit**

```bash
git add src/nexus/cache/backends.py tests/fakes/fake_clock.py tests/fakes/__init__.py tests/test_cache_backends.py && git commit -m "feat(cache): InMemoryBackend + DiskBackend + FakeClock"
```

---

## Task 4: Implement decorator.py + FakeCacheBackend + wire __init__.py

**Files:**
- Create: `src/nexus/cache/decorator.py`
- Modify: `src/nexus/cache/__init__.py`
- Create: `tests/fakes/fake_cache_backend.py`
- Modify: `tests/fakes/__init__.py`
- Create: `tests/test_cache_decorator.py`

- [ ] **Step 1: Create FakeCacheBackend**

Write `tests/fakes/fake_cache_backend.py`:

```python
# tests/fakes/fake_cache_backend.py
# CacheBackend test double. Records every call. No real storage.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeCacheBackend: real fake (no mocks) implementing CacheBackend Protocol."""

from dataclasses import dataclass, field

from nexus.cache.backends import MISSING

__all__ = ["FakeCacheBackend"]


@dataclass(slots=True)
class FakeCacheBackend:
    """Records every get/set/delete/clear. Returns the most recent set value.

    Attributes:
        store: Visible dict of stored entries; tests can assert on it directly.
        gets: List of keys passed to get().
        sets: List of (key, value, ttl) tuples passed to set().
        deletes: List of keys passed to delete().
        clears: Count of clear() calls.
    """

    store: dict[str, object] = field(default_factory=dict)
    gets: list[str] = field(default_factory=list)
    sets: list[tuple[str, object, int | None]] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)
    clears: int = 0

    def get(self, key: str) -> object:
        """See CacheBackend.get."""
        self.gets.append(key)
        return self.store.get(key, MISSING)

    def set(self, key: str, value: object, ttl: int | None) -> None:
        """See CacheBackend.set."""
        self.sets.append((key, value, ttl))
        self.store[key] = value

    def delete(self, key: str) -> None:
        """See CacheBackend.delete."""
        self.deletes.append(key)
        self.store.pop(key, None)

    def clear(self) -> None:
        """See CacheBackend.clear."""
        self.clears += 1
        self.store.clear()
```

- [ ] **Step 2: Update tests/fakes/__init__.py**

```python
# tests/fakes/__init__.py
# Fake implementations used in tests. No mocks anywhere.
# Author: Pierre Grothe
# Date: 2026-05-07
"""Fake connectors and clients for use in tests."""

from tests.fakes.fake_agent_client import FakeAgentClient
from tests.fakes.fake_cache_backend import FakeCacheBackend
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_keychain import FakeKeychainClient
from tests.fakes.fake_sn_client import FakeServiceNowClient

__all__ = [
    "FakeAgentClient",
    "FakeCacheBackend",
    "FakeClock",
    "FakeKeychainClient",
    "FakeServiceNowClient",
]
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_cache_decorator.py`:

```python
# tests/test_cache_decorator.py
# Tests for the @cached decorator and clear_cache.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Tests for nexus.cache.decorator."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from nexus.cache import cached, clear_cache
from nexus.cache.errors import CacheKeyError


def test_cached_requires_explicit_ttl_keyword() -> None:
    # Bind `cached` through a permissive Any reference so static analysis
    # tolerates the deliberately-missing ttl kwarg used to assert TypeError.
    cached_factory: Any = cached
    with pytest.raises(TypeError, match="ttl"):
        cached_factory()


def test_cached_persist_requires_namespace() -> None:
    with pytest.raises(ValueError, match="namespace"):

        @cached(ttl=60, persist=True)
        def _f() -> int:
            return 1


def test_cached_sync_function_returns_cached_value_on_second_call() -> None:
    calls = 0

    @cached(ttl=None)
    def compute(x: int) -> int:
        nonlocal calls
        calls += 1
        return x * 2

    assert compute(3) == 6
    assert compute(3) == 6
    assert calls == 1


def test_cached_sync_function_with_different_args_calls_through() -> None:
    calls = 0

    @cached(ttl=None)
    def compute(x: int) -> int:
        nonlocal calls
        calls += 1
        return x * 2

    compute(1)
    compute(2)
    assert calls == 2


async def test_cached_async_function_returns_cached_value_on_second_call() -> None:
    calls = 0

    @cached(ttl=None)
    async def fetch(x: int) -> int:
        nonlocal calls
        calls += 1
        return x + 1

    assert await fetch(5) == 6
    assert await fetch(5) == 6
    assert calls == 1


def test_cached_method_scope_is_per_instance() -> None:
    class Counter:
        def __init__(self) -> None:
            self.calls = 0

        @cached(ttl=None)
        def value(self) -> int:
            self.calls += 1
            return self.calls

    a = Counter()
    b = Counter()
    a.value()
    a.value()
    b.value()
    assert a.calls == 1
    assert b.calls == 1


def test_cached_method_works_on_frozen_dataclass() -> None:
    @dataclass(slots=True, frozen=True)
    class Frozen:
        x: int

        @cached(ttl=None)
        def doubled(self) -> int:
            return self.x * 2

    f = Frozen(x=5)
    assert f.doubled() == 10
    assert f.doubled() == 10  # second call hits cache, no AttributeError


def test_cached_does_not_cache_exceptions() -> None:
    calls = 0

    @cached(ttl=None)
    def boom() -> int:
        nonlocal calls
        calls += 1
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        boom()
    with pytest.raises(RuntimeError):
        boom()
    assert calls == 2


def test_cached_with_unhashable_arg_raises_cache_key_error() -> None:
    @cached(ttl=None)
    def f(payload: dict[str, int]) -> int:
        return sum(payload.values())

    with pytest.raises(CacheKeyError):
        f({"a": 1})


def test_cached_with_key_fn_handles_unhashable_arg() -> None:
    calls = 0

    @cached(ttl=None, key_fn=lambda payload: ",".join(sorted(payload)))
    def f(payload: dict[str, int]) -> int:
        nonlocal calls
        calls += 1
        return sum(payload.values())

    assert f({"a": 1, "b": 2}) == 3
    assert f({"a": 99, "b": 99}) == 3  # same keys -> same cache key -> cache hit
    assert calls == 1


def test_cached_persist_writes_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.cache import decorator as decorator_module

    monkeypatch.setattr(decorator_module, "_disk_cache_root", lambda: tmp_path)
    calls = 0

    @cached(ttl=None, persist=True, namespace="test_ns")
    def heavy(x: int) -> int:
        nonlocal calls
        calls += 1
        return x * 10

    assert heavy(3) == 30
    assert heavy(3) == 30
    assert calls == 1


def test_cached_persist_survives_redecoration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-decorating the same qualname under the same namespace hits the disk store."""
    from nexus.cache import decorator as decorator_module

    monkeypatch.setattr(decorator_module, "_disk_cache_root", lambda: tmp_path)
    populate_calls = 0

    def populate() -> None:
        nonlocal populate_calls

        @cached(ttl=None, persist=True, namespace="redecorate_ns")
        def fetch(x: int) -> int:
            nonlocal populate_calls
            populate_calls += 1
            return x * 10

        fetch(3)

    populate()  # writes to disk under "redecorate_ns" + qualname
    populate()  # re-decorates; cache key stays the same; underlying call skipped
    assert populate_calls == 1


def test_clear_cache_method_clears_one_method_across_instances() -> None:
    class Counter:
        def __init__(self) -> None:
            self.calls = 0

        @cached(ttl=None)
        def value(self) -> int:
            self.calls += 1
            return self.calls

    a = Counter()
    a.value()  # populates cache for `a`
    clear_cache(Counter.value)
    a.value()  # cache cleared, calls underlying again
    assert a.calls == 2


def test_clear_cache_instance_clears_all_methods_on_instance() -> None:
    class Multi:
        def __init__(self) -> None:
            self.a_calls = 0
            self.b_calls = 0

        @cached(ttl=None)
        def a(self) -> int:
            self.a_calls += 1
            return self.a_calls

        @cached(ttl=None)
        def b(self) -> int:
            self.b_calls += 1
            return self.b_calls

    obj = Multi()
    obj.a()
    obj.b()
    clear_cache(obj)
    obj.a()
    obj.b()
    assert obj.a_calls == 2
    assert obj.b_calls == 2


def test_clear_cache_no_arg_clears_all_module_level_caches() -> None:
    calls = 0

    @cached(ttl=None)
    def f() -> int:
        nonlocal calls
        calls += 1
        return calls

    f()
    clear_cache()
    f()
    assert calls == 2
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_cache_decorator.py -v --override-ini="addopts="
```

Expected: ImportError on `cached` from `nexus.cache`.

- [ ] **Step 5: Implement decorator.py**

Write `src/nexus/cache/decorator.py`:

```python
# src/nexus/cache/decorator.py
# The @cached decorator and clear_cache function. ADR-017.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Single canonical caching decorator for NEXUS.

Use @cached(ttl=...) for in-process caching. Use @cached(ttl=..., persist=True,
namespace="...") for disk-persistent caching.
"""

import functools
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import ParamSpec, TypeVar, cast
from weakref import WeakKeyDictionary

from nexus.cache.backends import MISSING, CacheBackend, DiskBackend, InMemoryBackend
from nexus.cache.keys import compute_key

__all__ = ["cached", "clear_cache"]

P = ParamSpec("P")
R = TypeVar("R")

# Permissive callable alias used only inside this module for the registries
# below. The decorator preserves the wrapped function's true signature via cast().
_AnyCallable = Callable[..., object]

# Module-level registries -- populated as decorators are applied.
# Key: the decorated function (closure-stable). Value: the registry record.
_FREE_FUNCTION_BACKENDS: dict[_AnyCallable, InMemoryBackend] = {}
_INSTANCE_BACKENDS: dict[_AnyCallable, "WeakKeyDictionary[object, InMemoryBackend]"] = {}
_DISK_BACKENDS: dict[str, DiskBackend] = {}


def _disk_cache_root() -> Path:
    """Return the directory that hosts disk caches.

    Tests monkeypatch this. Production resolves to NexusPaths.from_env().root /
    "cache" -- but that lookup is deferred to first use to avoid creating the
    directory at import time.
    """
    from nexus.config.paths import NexusPaths  # noqa: PLC0415  -- intentional, deferred

    return NexusPaths.from_env().root / "cache"


def cached(
    *,
    ttl: int | None,
    persist: bool = False,
    namespace: str | None = None,
    key_fn: Callable[..., str] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Cache the result of a function or method.

    Args:
        ttl: Seconds the entry stays fresh. None = no expiry within process.
            Required keyword.
        persist: If True, the cache is backed by diskcache and survives across
            runs. Requires ``namespace``.
        namespace: Required when persist=True. Acts as a prefix for disk keys.
        key_fn: Optional callable that takes (*args, **kwargs) and returns a
            string. Used in place of the default arg-hashing.

    Returns:
        The decorator.

    Raises:
        ValueError: At decoration time if persist=True and namespace is None.
        CacheKeyError: At call time if an arg is not hashable and no key_fn is
            given.
    """
    if persist and not namespace:
        raise ValueError(
            "persist=True requires namespace=. See ADR-017."
        )

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        is_async = inspect.iscoroutinefunction(func)
        sig = inspect.signature(func)
        params = list(sig.parameters)
        is_method = bool(params) and params[0] in ("self", "cls")

        if persist:
            backend = _get_or_create_disk_backend(namespace)
            return _wrap_with_backend(
                func,
                lambda first_arg: backend,
                ttl=ttl,
                namespace=namespace,
                key_fn=key_fn,
                is_async=is_async,
                is_method=is_method,
            )

        if is_method:
            registry: WeakKeyDictionary[object, InMemoryBackend] = WeakKeyDictionary()
            _INSTANCE_BACKENDS[func] = registry

            def get_backend(first_arg: object) -> CacheBackend:
                if first_arg not in registry:
                    registry[first_arg] = InMemoryBackend()
                return registry[first_arg]

            return _wrap_with_backend(
                func,
                get_backend,
                ttl=ttl,
                namespace=None,
                key_fn=key_fn,
                is_async=is_async,
                is_method=True,
            )

        backend = InMemoryBackend()
        _FREE_FUNCTION_BACKENDS[func] = backend
        return _wrap_with_backend(
            func,
            lambda first_arg: backend,
            ttl=ttl,
            namespace=None,
            key_fn=key_fn,
            is_async=is_async,
            is_method=False,
        )

    return decorator


def _wrap_with_backend(
    func: Callable[P, R],
    get_backend: Callable[[object], CacheBackend],
    *,
    ttl: int | None,
    namespace: str | None,
    key_fn: Callable[..., str] | None,
    is_async: bool,
    is_method: bool,
) -> Callable[P, R]:
    """Wrap func so it consults a backend before calling through."""
    # The wrappers below take *args: object / **kwargs: object because the
    # decorator runs against arbitrary functions and the project's strict
    # rules forbid Any in signatures. We cast the result back to Callable[P, R]
    # at the boundary so callers see the wrapped function's true signature.
    permissive_func = cast("Callable[..., object]", func)

    if is_async:

        @functools.wraps(func)
        async def async_wrapper(*args: object, **kwargs: object) -> object:
            first_arg = args[0] if (is_method and args) else None
            backend = get_backend(first_arg)
            cache_args = args[1:] if is_method else args
            key = compute_key(
                func, args=cache_args, kwargs=kwargs, namespace=namespace, key_fn=key_fn
            )
            cached_value = backend.get(key)
            if cached_value is not MISSING:
                return cached_value
            result = await permissive_func(*args, **kwargs)
            backend.set(key, result, ttl)
            return result

        return cast("Callable[P, R]", async_wrapper)

    @functools.wraps(func)
    def sync_wrapper(*args: object, **kwargs: object) -> object:
        first_arg = args[0] if (is_method and args) else None
        backend = get_backend(first_arg)
        cache_args = args[1:] if is_method else args
        key = compute_key(
            func, args=cache_args, kwargs=kwargs, namespace=namespace, key_fn=key_fn
        )
        cached_value = backend.get(key)
        if cached_value is not MISSING:
            return cached_value
        result = permissive_func(*args, **kwargs)
        backend.set(key, result, ttl)
        return result

    return cast("Callable[P, R]", sync_wrapper)


def _get_or_create_disk_backend(namespace: str | None) -> DiskBackend:
    """Return the shared DiskBackend for ``namespace``. Lazy-init."""
    assert namespace is not None  # checked by caller
    if namespace not in _DISK_BACKENDS:
        cache_dir = _disk_cache_root() / namespace
        cache_dir.mkdir(parents=True, exist_ok=True)
        _DISK_BACKENDS[namespace] = DiskBackend(cache_dir=cache_dir)
    return _DISK_BACKENDS[namespace]


def clear_cache(target: object | None = None) -> None:
    """Clear caches.

    - clear_cache(method): clear that method's cache for every instance.
    - clear_cache(instance): clear all cached methods on that instance.
    - clear_cache(): clear every module-level (free-function) cache.

    Args:
        target: A method, an instance, or None.
    """
    if target is None:
        for backend in _FREE_FUNCTION_BACKENDS.values():
            backend.clear()
        return

    if callable(target) and target in _INSTANCE_BACKENDS:
        for backend in _INSTANCE_BACKENDS[target].values():
            backend.clear()
        return

    if callable(target) and target in _FREE_FUNCTION_BACKENDS:
        _FREE_FUNCTION_BACKENDS[target].clear()
        return

    # Treat as instance: clear every method's backend on this instance.
    for registry in _INSTANCE_BACKENDS.values():
        backend = registry.get(target)
        if backend is not None:
            backend.clear()
```

- [ ] **Step 6: Update src/nexus/cache/__init__.py**

```python
# src/nexus/cache/__init__.py
# Layer-0 caching utility -- exports the @cached decorator, clear_cache, and CacheKeyError.
# Author: Pierre Grothe
# Date: 2026-05-08
"""NEXUS canonical caching decorator (ADR-017).

All caching in src/nexus/ goes through @cached. Direct use of functools.cache,
functools.lru_cache, and functools.cached_property is forbidden by Semgrep.
"""

from nexus.cache.decorator import cached, clear_cache
from nexus.cache.errors import CacheKeyError

__all__ = ["CacheKeyError", "cached", "clear_cache"]
```

- [ ] **Step 7: Run tests**

```bash
.venv/bin/pytest tests/test_cache_decorator.py -v --override-ini="addopts="
```

Expected: 14 passed.

- [ ] **Step 8: Run full cache test suite + lint + types**

```bash
.venv/bin/pytest tests/test_cache_keys.py tests/test_cache_backends.py tests/test_cache_decorator.py -q --override-ini="addopts="
.venv/bin/ruff check src/nexus/cache/ tests/test_cache_decorator.py tests/fakes/fake_cache_backend.py
.venv/bin/mypy src/nexus/cache/
.venv/bin/pyright src/nexus/cache/
```

Expected: 35 passing total; 0 ruff violations; 0 mypy errors; 0 pyright errors.

The implementation in Step 5 already uses `cast("Callable[P, R]", wrapper)` at the boundaries and a single `permissive_func = cast("Callable[..., object]", func)` for the inner call. There are no `# type: ignore` comments anywhere in `src/nexus/cache/`. If mypy or pyright report errors, re-read Step 5's code -- do NOT add `# type: ignore` to silence them; that is project-blocked by ADR-007.

- [ ] **Step 9: Commit**

```bash
git add src/nexus/cache/decorator.py src/nexus/cache/__init__.py tests/fakes/fake_cache_backend.py tests/fakes/__init__.py tests/test_cache_decorator.py && git commit -m "feat(cache): @cached decorator + clear_cache + FakeCacheBackend"
```

---

## Task 5: Add Semgrep rules for caching governance

**Files:**
- Modify: `.semgrep/rules.yml`

- [ ] **Step 1: Add the three rules to .semgrep/rules.yml**

Append to the existing `rules:` list:

```yaml
  - id: caching-must-use-cached-decorator
    languages: [python]
    severity: ERROR
    message: |
      Direct use of functools.cache, functools.lru_cache, and
      functools.cached_property is forbidden in src/nexus/. Use the
      @cached decorator from nexus.cache (ADR-017).
    paths:
      include:
        - "src/nexus/**"
    pattern-either:
      - pattern: "@cache"
      - pattern: "@functools.cache"
      - pattern: "@cached_property"
      - pattern: "@functools.cached_property"
      - pattern: "@lru_cache"
      - pattern: "@lru_cache(...)"
      - pattern: "@functools.lru_cache"
      - pattern: "@functools.lru_cache(...)"
    metadata:
      adr: ADR-017
      category: governance

  - id: cached-requires-explicit-ttl
    languages: [python]
    severity: ERROR
    message: |
      @cached requires an explicit ttl= keyword. Use ttl=None for
      infinite-within-process caching, or ttl=N for a TTL in seconds.
      See ADR-017.
    pattern-either:
      - pattern: "@cached()"
      - pattern: "@cached(persist=...)"
      - pattern: "@cached(persist=..., namespace=...)"
      - pattern: "@cached(namespace=...)"
      - pattern: "@cached(key_fn=...)"
      - pattern: "@cached(persist=..., key_fn=...)"
      - pattern: "@cached(persist=..., namespace=..., key_fn=...)"
      - pattern: "@cached(namespace=..., key_fn=...)"
    metadata:
      adr: ADR-017
      category: governance

  - id: cached-persist-requires-namespace
    languages: [python]
    severity: ERROR
    message: |
      @cached(persist=True) requires namespace=. The namespace becomes the
      disk-cache key prefix and prevents collisions between modules.
      See ADR-017.
    pattern-either:
      - pattern: "@cached(ttl=..., persist=True)"
      - pattern: "@cached(ttl=..., persist=True, key_fn=...)"
    metadata:
      adr: ADR-017
      category: governance
```

- [ ] **Step 2: Test against synthetic violations**

```bash
cat > /tmp/sg_violation_1.py <<'EOF'
from functools import cache

@cache
def bad() -> int:
    return 1
EOF
/Users/pierre.grothe/.local/bin/semgrep --config .semgrep/rules.yml /tmp/sg_violation_1.py --error 2>&1 | tail -10
rm /tmp/sg_violation_1.py
```

Expected: `caching-must-use-cached-decorator` fires. (The path filter `src/nexus/**` won't match `/tmp/`. To verify the rule logic, temporarily place the test file under `src/nexus/` and re-run, then delete.)

Cleaner verification:

```bash
mkdir -p /tmp/sg_test/src/nexus
cat > /tmp/sg_test/src/nexus/violation.py <<'EOF'
from functools import cache

@cache
def bad() -> int:
    return 1
EOF
cd /tmp/sg_test && /Users/pierre.grothe/.local/bin/semgrep --config /Users/pierre.grothe/Developer/nexus/.semgrep/rules.yml src/ --error 2>&1 | tail -15
cd /Users/pierre.grothe/Developer/nexus && rm -rf /tmp/sg_test
```

Expected: 1 finding -- `caching-must-use-cached-decorator`.

- [ ] **Step 3: Verify no false positives in the project**

```bash
/Users/pierre.grothe/.local/bin/semgrep --config .semgrep/rules.yml src/ tests/ --error
```

Expected: 0 findings (Task 4's @cached usages are all `ttl=...` and namespace-correct).

- [ ] **Step 4: Run pre-commit**

```bash
.venv/bin/pre-commit run --all-files 2>&1 | tail -10
```

Expected: all 6 hooks pass.

- [ ] **Step 5: Commit**

```bash
git add .semgrep/rules.yml && git commit -m "feat(cache): semgrep governance rules for @cached (ADR-017)"
```

---

## Task 6: Adopt @cached on ConfigManager.read() and NexusPaths.from_env()

**Files:**
- Modify: `src/nexus/config/manager.py`
- Modify: `src/nexus/config/paths.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Read the current ConfigManager**

```bash
grep -n "def read\|class ConfigManager\|^import\|^from" src/nexus/config/manager.py | head -15
```

Note the `read()` signature so the decorator stays compatible.

- [ ] **Step 2: Adopt @cached on ConfigManager.read()**

Edit `src/nexus/config/manager.py`. Add to the imports:

```python
from nexus.cache import cached
```

Decorate `read()`:

```python
    @cached(ttl=None)
    def read(self) -> NexusConfig:
        """Existing docstring stays."""
        # Existing body unchanged.
```

- [ ] **Step 3: Adopt @cached on NexusPaths.from_env()**

Edit `src/nexus/config/paths.py`. Add the import:

```python
from nexus.cache import cached
```

Decorate `from_env()`:

```python
    @classmethod
    @cached(ttl=None)
    def from_env(cls) -> NexusPaths:
        """Existing docstring stays."""
        # Existing body unchanged.
```

(`@classmethod` goes outermost. The `cls` arg is the cache scope -- shared across all instances of NexusPaths.)

- [ ] **Step 4: Add cache-hit assertion test**

Read the existing `tests/test_config.py`. Append a new test that proves the decorator is wired:

```python
def test_config_manager_read_caches_after_first_call(tmp_path: pytest.TempPathFactory) -> None:
    """Calling read() twice should hit disk only once."""
    from nexus.cache import clear_cache
    from nexus.config.manager import ConfigManager

    config_path = tmp_path / "config.yaml"
    config_path.write_text("default_org: servicenow\n", encoding="utf-8")
    manager = ConfigManager(config_path=config_path)

    # First read: populates cache. Second read: cache hit.
    first = manager.read()
    config_path.write_text("default_org: changed\n", encoding="utf-8")
    second = manager.read()

    assert first == second  # cache served the first value, not the disk change
    assert second.default_org == "servicenow"  # not "changed"

    # After clear_cache(manager), the new disk value is read.
    clear_cache(manager)
    third = manager.read()
    assert third.default_org == "changed"
```

(If `tmp_path` is the wrong fixture name in the existing tests, match the convention used there. The test verifies cache hit by mutating disk between calls -- a cache-served result will be stale; an uncached read would see the change.)

- [ ] **Step 5: Run the targeted tests**

```bash
.venv/bin/pytest tests/test_config.py -v --override-ini="addopts="
```

Expected: all existing tests pass + the new one passes.

- [ ] **Step 6: Lint + types**

```bash
.venv/bin/ruff check src/nexus/config/ tests/test_config.py
.venv/bin/mypy src/nexus/config/ tests/test_config.py
.venv/bin/pyright src/nexus/config/ tests/test_config.py
```

Expected: 0 violations, 0 errors.

- [ ] **Step 7: Run pre-commit**

```bash
.venv/bin/pre-commit run --all-files 2>&1 | tail -10
```

Expected: 6/6 pass.

- [ ] **Step 8: Commit**

```bash
git add src/nexus/config/manager.py src/nexus/config/paths.py tests/test_config.py && git commit -m "feat(config): adopt @cached on ConfigManager.read and NexusPaths.from_env"
```

---

## Task 7: Update governance docs (ratchet, governance.md, patterns.md, ADR-017, decisions.md)

**Files:**
- Modify: `.ratchet.json`
- Create: `.primer/adr/ADR-017-canonical-caching-decorator.md`
- Modify: `.primer/governance.md`
- Modify: `.primer/patterns.md`
- Modify: `.primer/decisions.md`

- [ ] **Step 1: Generate coverage numbers for the new modules**

```bash
.venv/bin/pytest --cov=nexus --cov-report=json --cov-fail-under=0 -q --override-ini="addopts="
.venv/bin/python -c "
import json
data = json.load(open('coverage.json'))
for path, info in sorted(data['files'].items()):
    if 'nexus/cache/' in path or 'nexus/config/manager' in path:
        s = info['summary']
        print(path, '-> covered=' + str(s['covered_lines']), 'total=' + str(s['num_statements']))
"
```

Note the numbers for: `nexus/cache/__init__.py`, `nexus/cache/errors.py`, `nexus/cache/keys.py`, `nexus/cache/backends.py`, `nexus/cache/decorator.py`, and the updated `nexus/config/manager.py`.

- [ ] **Step 2: Update .ratchet.json**

Add 5 new entries (using the actual numbers from Step 1) and update `nexus.config.manager`:

```json
    "nexus.cache": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.cache.backends": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.cache.decorator": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.cache.errors": {"covered_lines": <N>, "total_lines": <N>},
    "nexus.cache.keys": {"covered_lines": <N>, "total_lines": <N>},
```

And bump `nexus.config.manager` to its new covered/total values.

- [ ] **Step 3: Create ADR-017**

Write `.primer/adr/ADR-017-canonical-caching-decorator.md`:

```markdown
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

Per-instance scope: each cached method holds a WeakKeyDictionary in its
closure mapping instances to InMemoryBackend instances. Works for plain
classes, frozen dataclasses, frozen Pydantic models, and slots+frozen
dataclasses (where setattr-on-self would fail).

Free functions: backend is a module-level InMemoryBackend created once at
decoration time.

## Consequences

  - One mental model for caching across the codebase.
  - One place to add observability (cache hit rate, eviction stats) when
    that becomes a need (deferred per spec).
  - Adds `diskcache >= 5.6` as a runtime dependency.
  - Instances cached by @cached must be hashable. Default for plain classes
    and frozen dataclasses; custom mutable classes that override __eq__
    without __hash__ would fail. Documented constraint.
  - Function exceptions are NEVER cached; they are always re-raised.
  - Migration to actual cache adoption is staged: ConfigManager.read and
    NexusPaths.from_env land with this ADR. MCPProbe, ServiceNowClient,
    and AgentClient adopt later in their own PRs.

Spec: docs/superpowers/specs/2026-05-08-cached-decorator-design.md
Plan: docs/superpowers/plans/2026-05-08-cached-decorator.md
```

- [ ] **Step 4: Update .primer/governance.md**

Add three new lines under "Tier 1 -- Blocking (semgrep, semantic governance, ADR-016)":

```markdown
- caching-must-use-cached-decorator -- @cache, @lru_cache, @cached_property forbidden in src/nexus/ (ADR-017)
- cached-requires-explicit-ttl -- @cached without ttl= is forbidden (ADR-017)
- cached-persist-requires-namespace -- @cached(persist=True) without namespace= is forbidden (ADR-017)
```

Add to the ADR catalog (after ADR-016):

```markdown
| 017 | Single canonical caching decorator (@cached) | semgrep + python | accepted |
```

- [ ] **Step 5: Update .primer/patterns.md**

In the "Layer dependency rule" section, add cache as Layer 0 at the top of the dependency listing:

```
  cache -> (nothing in nexus)
  config -> cache
  auth -> config, cache
  capabilities -> config, auth, cache
  api -> capabilities, cache
  connectors -> cache
  ...
```

(Adjust the existing entries to add `cache` to each layer's allowed-imports list.)

- [ ] **Step 6: Append to .primer/decisions.md**

Append:

```markdown


---

### 2026-05-08 -- Single canonical caching decorator (@cached)

**Status:** accepted (ADR-017)

**Context:** Four families of operations in NEXUS benefit from caching
(Agent SDK calls, ServiceNow API responses, capability probes, config
lookups). Without a canonical decorator, each would invent its own layer
with different semantics.

**Decision:** Layer-0 utility `src/nexus/cache/` exports `@cached(ttl,
persist, namespace, key_fn)` and `clear_cache(target)`. Three Semgrep rules
plus runtime TypeError/ValueError enforce the contract.

**Consequences:** Adds diskcache as a runtime dep. Instances must be
hashable. Function exceptions never cached. ADR-017 documents the design;
spec at docs/superpowers/specs/2026-05-08-cached-decorator-design.md;
plan at docs/superpowers/plans/2026-05-08-cached-decorator.md.
```

- [ ] **Step 7: Run pre-commit**

```bash
.venv/bin/pre-commit run --all-files 2>&1 | tail -10
```

Expected: 6/6 pass.

- [ ] **Step 8: Commit**

```bash
git add .ratchet.json .primer/ && git commit -m "docs: ADR-017 canonical caching decorator + governance + ratchet"
```

---

## Task 8: Push, open PR, manual verification

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/cached-decorator
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "feat: canonical @cached decorator (ADR-017)" --body "$(cat <<'EOF'
## Summary

- New Layer-0 package src/nexus/cache/ with @cached decorator and clear_cache.
- InMemoryBackend (with injectable clock for tests) + DiskBackend (diskcache).
- Per-instance scope via WeakKeyDictionary -- works on frozen+slots dataclasses.
- 3 Semgrep rules enforcing the canonical decorator (ADR-017).
- Initial adoption: ConfigManager.read and NexusPaths.from_env.
- Adds diskcache >= 5.6 as a runtime dependency.

## Why

Standardize on one caching API. Block @functools.cache, @lru_cache, and
@cached_property in src/nexus/ via Semgrep. Enforce explicit TTL and
namespace at both Semgrep and Python-runtime layers (defense in depth).

Spec: docs/superpowers/specs/2026-05-08-cached-decorator-design.md
Plan: docs/superpowers/plans/2026-05-08-cached-decorator.md
ADR-017: .primer/adr/ADR-017-canonical-caching-decorator.md

## Test plan

- [x] 35 new tests in tests/test_cache_*.py (keys, backends, decorator)
- [x] Existing tests still pass; ConfigManager.read cache-hit assertion added
- [x] All 6 pre-commit hooks pass (black, ruff, mypy, pyright, semgrep, pytest)
- [x] Semgrep rules verified against synthetic violations + zero project-level findings

## Out of scope (deferred)

- @cached adoption on MCPProbe, ServiceNowClient, AgentClient (separate PRs).
- Cache stats / observability -- when there's a debugging need.
- Cache versioning on SDK upgrades -- caller's responsibility for now.

EOF
)"
```

Expected: PR URL printed.

---

## Self-Review Notes

- All 8 tasks have explicit code and exact commands. No placeholders.
- Type consistency: `cached(*, ttl, persist, namespace, key_fn)` signature
  is identical across Task 4 (decorator), Task 5 (Semgrep patterns), Task 6
  (adoption), and Task 7 (ADR/decisions).
- TDD ordering: every code task writes a failing test, runs it (Step 2 of
  the task), implements minimally (Step 3+), reruns to pass.
- File ownership: each module has one job (errors.py = exception, keys.py =
  key generation, backends.py = storage Protocol + 2 impls, decorator.py =
  decorator + clear_cache).
- Spec coverage:
  - Architecture (spec) -> Tasks 1-4 build the module
  - API (spec) -> Tasks 4 implements all signatures
  - Cache key generation (spec) -> Task 2
  - Self handling via WeakKeyDictionary (spec, post-correction) -> Task 4
  - Governance + 3 Semgrep rules (spec) -> Tasks 5 + 7
  - Testing strategy with FakeClock + FakeCacheBackend (spec) -> Tasks 3 + 4
  - Migration plan: ConfigManager + NexusPaths (spec) -> Task 6
  - ADR-017 + governance + decisions (spec) -> Task 7
- Risk: Task 4's decorator will exercise mypy/pyright strict more than other
  modules due to async/sync wrapper polymorphism. Step 8 of Task 4 explicitly
  flags the type-system path and the no-type-ignore policy; the cleanest
  resolution is a single `cast` per branch.
