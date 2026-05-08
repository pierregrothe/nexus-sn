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
