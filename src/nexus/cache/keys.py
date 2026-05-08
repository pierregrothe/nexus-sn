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
    if any(_is_known_unhashable(a) for a in args):
        offending = next(type(a).__name__ for a in args if _is_known_unhashable(a))
        raise CacheKeyError(
            f"@cached received unhashable arg of type {offending!r}; "
            "declare key_fn=lambda ... on the decorator (ADR-017)."
        )
    try:
        payload = repr(args) + "|" + repr(sorted_kwargs)
    except Exception as exc:
        raise CacheKeyError(f"could not produce stable repr for args: {exc}") from exc
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return digest[:_HASH_LEN]


def _is_known_unhashable(obj: object) -> bool:
    """Return True for dict/list/set -- mutable containers we refuse to hash."""
    return isinstance(obj, (dict, list, set))
