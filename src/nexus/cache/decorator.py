# src/nexus/cache/decorator.py
# The @cached decorator and clear_cache function. ADR-017.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Single canonical caching decorator for NEXUS.

Use @cached(ttl=...) for in-process caching. Use @cached(ttl=..., persist=True,
namespace="...") for disk-persistent caching.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast
from weakref import WeakKeyDictionary

from nexus.cache.backends import MISSING, CacheBackend, DiskBackend, InMemoryBackend
from nexus.cache.keys import compute_key

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["cached", "clear_cache"]

# Permissive callable alias used only inside this module for the registries
# below. The decorator preserves the wrapped function's true signature via cast().
type _AnyCallable = Callable[..., object]


class _InstanceRegistry:
    """Per-method registry mapping instances to InMemoryBackend.

    Prefers WeakKeyDictionary so backends are dropped when the instance is
    collected. Frozen+slots dataclasses don't support weak references, so we
    fall back to a regular dict keyed by id() for those. The fallback leaks
    backends until clear_cache() runs, which is acceptable for the rare
    frozen+slots case (per ADR-017).
    """

    __slots__ = ("_strong", "_weak")

    def __init__(self) -> None:
        """Initialize the empty weak and strong stores."""
        self._weak: WeakKeyDictionary[object, InMemoryBackend] = WeakKeyDictionary()
        self._strong: dict[int, InMemoryBackend] = {}

    def get_or_create(self, instance: object) -> InMemoryBackend:
        """Return the backend for ``instance``, creating one if absent."""
        try:
            backend = self._weak.get(instance)
            if backend is None:
                backend = InMemoryBackend()
                self._weak[instance] = backend
            return backend
        except TypeError:
            key = id(instance)
            backend = self._strong.get(key)
            if backend is None:
                backend = InMemoryBackend()
                self._strong[key] = backend
            return backend

    def lookup(self, instance: object) -> InMemoryBackend | None:
        """Return the backend for ``instance`` if present, else None."""
        try:
            backend = self._weak.get(instance)
            if backend is not None:
                return backend
        except TypeError:
            pass
        return self._strong.get(id(instance))

    def all_backends(self) -> list[InMemoryBackend]:
        """Return every backend currently held in either store."""
        return [*self._weak.values(), *self._strong.values()]


# Module-level registries -- populated as decorators are applied.
# Keys are the *wrapper* callables that the decorator returns.
_FREE_FUNCTION_BACKENDS: dict[_AnyCallable, InMemoryBackend] = {}
_INSTANCE_BACKENDS: dict[_AnyCallable, _InstanceRegistry] = {}
_DISK_BACKENDS: dict[str, DiskBackend] = {}


def _disk_cache_root() -> Path:
    """Return the directory that hosts disk caches.

    Tests monkeypatch this. Production resolves to NexusPaths.from_env().root /
    "cache" -- but that lookup is deferred to first use to avoid creating the
    directory at import time.
    """
    from nexus.config.paths import NexusPaths  # noqa: PLC0415

    return NexusPaths.from_env().root / "cache"


def cached[**P, R](
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
        raise ValueError("persist=True requires namespace=. See ADR-017.")

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        is_async = inspect.iscoroutinefunction(func)
        sig = inspect.signature(func)
        params = list(sig.parameters)
        is_method = bool(params) and params[0] in ("self", "cls")
        permissive_func = cast("Callable[..., object]", func)

        if persist:
            disk_backend = _get_or_create_disk_backend(namespace)

            def get_disk_backend(_first_arg: object) -> CacheBackend:
                return disk_backend

            return _wrap_with_backend(
                func,
                permissive_func,
                get_disk_backend,
                ttl=ttl,
                namespace=namespace,
                key_fn=key_fn,
                is_async=is_async,
                is_method=is_method,
            )

        if is_method:
            registry = _InstanceRegistry()

            def get_instance_backend(first_arg: object) -> CacheBackend:
                return registry.get_or_create(first_arg)

            wrapper = _wrap_with_backend(
                func,
                permissive_func,
                get_instance_backend,
                ttl=ttl,
                namespace=None,
                key_fn=key_fn,
                is_async=is_async,
                is_method=True,
            )
            _INSTANCE_BACKENDS[cast("_AnyCallable", wrapper)] = registry
            return wrapper

        free_backend = InMemoryBackend()

        def get_free_backend(_first_arg: object) -> CacheBackend:
            return free_backend

        wrapper = _wrap_with_backend(
            func,
            permissive_func,
            get_free_backend,
            ttl=ttl,
            namespace=None,
            key_fn=key_fn,
            is_async=is_async,
            is_method=False,
        )
        _FREE_FUNCTION_BACKENDS[cast("_AnyCallable", wrapper)] = free_backend
        return wrapper

    return decorator


def _wrap_with_backend[**P, R](
    func: Callable[P, R],
    permissive_func: Callable[..., object],
    get_backend: Callable[[object], CacheBackend],
    *,
    ttl: int | None,
    namespace: str | None,
    key_fn: Callable[..., str] | None,
    is_async: bool,
    is_method: bool,
) -> Callable[P, R]:
    """Wrap func so it consults a backend before calling through."""
    if is_async:
        async_call = cast("Callable[..., Awaitable[object]]", func)

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
            result = await async_call(*args, **kwargs)
            backend.set(key, result, ttl)
            return result

        return cast("Callable[P, R]", async_wrapper)

    @functools.wraps(func)
    def sync_wrapper(*args: object, **kwargs: object) -> object:
        first_arg = args[0] if (is_method and args) else None
        backend = get_backend(first_arg)
        cache_args = args[1:] if is_method else args
        key = compute_key(func, args=cache_args, kwargs=kwargs, namespace=namespace, key_fn=key_fn)
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

    if callable(target):
        if target in _INSTANCE_BACKENDS:
            for instance_backend in _INSTANCE_BACKENDS[target].all_backends():
                instance_backend.clear()
            return
        if target in _FREE_FUNCTION_BACKENDS:
            _FREE_FUNCTION_BACKENDS[target].clear()
            return

    # Treat as instance: clear every method's backend on this instance.
    for registry in _INSTANCE_BACKENDS.values():
        per_instance_backend = registry.lookup(target)
        if per_instance_backend is not None:
            per_instance_backend.clear()
