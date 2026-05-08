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


def _custom_key_fn(x: int) -> str:
    """Key function used by test_compute_key_uses_key_fn_when_provided."""
    return f"custom:{x}"


def test_compute_key_uses_key_fn_when_provided() -> None:
    key = compute_key(
        _func,
        args=(42,),
        kwargs={},
        namespace=None,
        key_fn=_custom_key_fn,
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
