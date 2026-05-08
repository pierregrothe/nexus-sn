# src/nexus/cache/backends.py
# Cache backend Protocol + InMemoryBackend + DiskBackend.
# Author: Pierre Grothe
# Date: 2026-05-08
"""Cache backends used by @cached.

InMemoryBackend lives in process; DiskBackend wraps the diskcache library
and persists across runs. Both implement CacheBackend Protocol.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import diskcache

__all__ = ["MISSING", "CacheBackend", "DiskBackend", "InMemoryBackend"]


class _Missing:
    """Sentinel type for "no cached value" -- distinct from None."""

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
    _store: dict[str, _Entry] = field(default_factory=dict[str, _Entry])

    def get(self, key: str) -> object:
        """Return the cached value or MISSING if absent or expired.

        Args:
            key: Cache key to look up.

        Returns:
            The cached value, or MISSING if absent or past TTL.
        """
        entry = self._store.get(key)
        if entry is None:
            return MISSING
        if entry.expires_at is not None and self.clock() >= entry.expires_at:
            del self._store[key]
            return MISSING
        return entry.value

    def set(self, key: str, value: object, ttl: int | None) -> None:
        """Store ``value`` under ``key`` with optional TTL.

        Args:
            key: Cache key.
            value: Value to cache (may be None).
            ttl: Seconds until expiry, or None for no expiry.
        """
        expires_at = None if ttl is None else self.clock() + ttl
        self._store[key] = _Entry(value=value, expires_at=expires_at)

    def delete(self, key: str) -> None:
        """Remove ``key`` from the cache. No-op if absent.

        Args:
            key: Cache key to remove.
        """
        self._store.pop(key, None)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        self._store.clear()


class DiskBackend:
    """Persistent cache backed by the diskcache library.

    Args:
        cache_dir: Directory for the sqlite-backed store. Created if absent.
    """

    def __init__(self, *, cache_dir: Path) -> None:
        """Open the diskcache at ``cache_dir``.

        Args:
            cache_dir: Filesystem path for the cache store.
        """
        self._cache: diskcache.Cache = diskcache.Cache(directory=str(cache_dir))

    def get(self, key: str) -> object:
        """Return the cached value or MISSING if absent or expired.

        Args:
            key: Cache key to look up.

        Returns:
            The cached value, or MISSING if absent.
        """
        return self._cache.get(key, default=MISSING)

    def set(self, key: str, value: object, ttl: int | None) -> None:
        """Store ``value`` under ``key`` with optional TTL.

        Args:
            key: Cache key.
            value: Value to cache (may be None).
            ttl: Seconds until expiry, or None for no expiry.
        """
        self._cache.set(key, value, expire=ttl)

    def delete(self, key: str) -> None:
        """Remove ``key`` from the cache. No-op if absent.

        Args:
            key: Cache key to remove.
        """
        self._cache.delete(key)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        self._cache.clear()
