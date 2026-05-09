# tests/fakes/fake_instance_registry.py
# In-memory fake for InstanceRegistry.
# Author: Pierre Grothe
# Date: 2026-05-08
"""FakeInstanceRegistry: in-memory substitute for InstanceRegistry."""

from dataclasses import dataclass, field

from nexus.instances.errors import InstanceNotFoundError
from nexus.instances.models import InstanceMeta, InstanceSnapshot

__all__ = ["FakeInstanceRegistry"]


@dataclass
class FakeInstanceRegistry:
    """In-memory substitute for InstanceRegistry.

    Attributes:
        profiles: Map of profile name to InstanceMeta.
        snapshots: Map of profile name to InstanceSnapshot.
    """

    profiles: dict[str, InstanceMeta] = field(default_factory=lambda: {})
    snapshots: dict[str, InstanceSnapshot] = field(default_factory=lambda: {})

    def register(self, meta: InstanceMeta) -> None:
        """Store meta in memory.

        Args:
            meta: Metadata for the new instance.
        """
        self.profiles[meta.profile] = meta

    def load(self, profile: str) -> InstanceMeta:
        """Return stored meta or raise InstanceNotFoundError.

        Args:
            profile: Profile name.

        Returns:
            Stored InstanceMeta.

        Raises:
            InstanceNotFoundError: If profile is not registered.
        """
        if profile not in self.profiles:
            raise InstanceNotFoundError(profile)
        return self.profiles[profile]

    def save(self, meta: InstanceMeta) -> None:
        """Overwrite stored meta or raise InstanceNotFoundError.

        Args:
            meta: Updated metadata to persist.

        Raises:
            InstanceNotFoundError: If profile is not registered.
        """
        if meta.profile not in self.profiles:
            raise InstanceNotFoundError(meta.profile)
        self.profiles[meta.profile] = meta

    def delete(self, profile: str) -> None:
        """Remove profile and its snapshot or raise InstanceNotFoundError.

        Args:
            profile: Profile name to delete.

        Raises:
            InstanceNotFoundError: If profile is not registered.
        """
        if profile not in self.profiles:
            raise InstanceNotFoundError(profile)
        del self.profiles[profile]
        self.snapshots.pop(profile, None)

    def list_all(self) -> list[InstanceMeta]:
        """Return all stored profiles.

        Returns:
            List of all registered InstanceMeta objects.
        """
        return sorted(self.profiles.values(), key=lambda m: m.profile)

    def load_snapshot(self, profile: str) -> InstanceSnapshot | None:
        """Return stored snapshot or None.

        Args:
            profile: Profile name.

        Returns:
            Stored InstanceSnapshot or None if not yet captured.
        """
        return self.snapshots.get(profile)

    def save_snapshot(self, profile: str, snapshot: InstanceSnapshot) -> None:
        """Store snapshot or raise InstanceNotFoundError.

        Args:
            profile: Profile name.
            snapshot: Snapshot to store.

        Raises:
            InstanceNotFoundError: If profile is not registered.
        """
        if profile not in self.profiles:
            raise InstanceNotFoundError(profile)
        self.snapshots[profile] = snapshot
