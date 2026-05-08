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

    store: dict[str, object] = field(default_factory=dict[str, object])
    gets: list[str] = field(default_factory=list[str])
    sets: list[tuple[str, object, int | None]] = field(
        default_factory=list[tuple[str, object, int | None]]
    )
    deletes: list[str] = field(default_factory=list[str])
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
