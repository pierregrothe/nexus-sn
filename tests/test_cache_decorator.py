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
from nexus.cache import decorator as decorator_module
from nexus.cache.errors import CacheKeyError


def test_cached_requires_explicit_ttl_keyword() -> None:
    # Bind `cached` through a permissive Any reference so static analysis
    # tolerates the deliberately-missing ttl kwarg used to assert TypeError.
    cached_factory: Any = cached
    with pytest.raises(TypeError, match="ttl"):
        cached_factory()


def test_cached_persist_requires_namespace() -> None:
    with pytest.raises(ValueError, match="namespace"):
        cached(ttl=60, persist=True)


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


def _key_by_keys(payload: dict[str, int]) -> str:
    return ",".join(sorted(payload))


def test_cached_with_key_fn_handles_unhashable_arg() -> None:
    calls = 0

    @cached(ttl=None, key_fn=_key_by_keys)
    def f(payload: dict[str, int]) -> int:
        nonlocal calls
        calls += 1
        return sum(payload.values())

    assert f({"a": 1, "b": 2}) == 3
    assert f({"a": 99, "b": 99}) == 3  # same keys -> same cache key -> cache hit
    assert calls == 1


def test_cached_persist_writes_to_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
