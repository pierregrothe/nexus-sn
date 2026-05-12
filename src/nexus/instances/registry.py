# src/nexus/instances/registry.py
# CRUD operations on the per-instance directory tree.
# Author: Pierre Grothe
# Date: 2026-05-08
"""InstanceRegistry: manages ~/.nexus/instances/<profile>/ directories."""

import logging
import shutil
import tempfile
from pathlib import Path

from pydantic import ValidationError

from nexus.instances.errors import InstanceNotFoundError
from nexus.instances.models import InstanceMeta, InstanceSnapshot
from nexus.plugins.models import PluginInventory

log = logging.getLogger(__name__)

__all__ = ["InstanceRegistry"]

_META = "meta.json"
_SNAPSHOT = "snapshot.json"
_PLUGIN_INVENTORY = "plugins.json"
_PLUGIN_BASELINE = "plugins.baseline.json"


class InstanceRegistry:
    """Read/write per-instance directories under a given root path.

    Args:
        instances_root: Root directory; typically NexusPaths.instances_dir.
    """

    def __init__(self, instances_root: Path) -> None:
        """See class docstring."""
        self._root = instances_root

    def register(self, meta: InstanceMeta) -> None:
        """Create the profile directory and write meta.json.

        Args:
            meta: Metadata for the new instance.
        """
        profile_dir = self._dir(meta.profile)
        profile_dir.mkdir(parents=True, exist_ok=True)
        (profile_dir / _META).write_text(meta.model_dump_json(indent=2), encoding="utf-8")
        log.info("registered instance profile=%s", meta.profile)

    def load(self, profile: str) -> InstanceMeta:
        """Read meta.json for a profile.

        Args:
            profile: Profile name.

        Returns:
            Validated InstanceMeta.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        meta_file = self._dir(profile) / _META
        if not meta_file.exists():
            raise InstanceNotFoundError(profile)
        return InstanceMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))

    def save(self, meta: InstanceMeta) -> None:
        """Overwrite meta.json for an existing profile.

        Args:
            meta: Updated metadata to persist.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(meta.profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(meta.profile)
        (profile_dir / _META).write_text(meta.model_dump_json(indent=2), encoding="utf-8")

    def delete(self, profile: str) -> None:
        """Remove the profile directory and all its contents.

        Args:
            profile: Profile name to delete.

        Raises:
            InstanceNotFoundError: If the profile does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        shutil.rmtree(profile_dir)
        log.info("deleted instance profile=%s", profile)

    def list_all(self) -> list[InstanceMeta]:
        """Return all registered profiles sorted by name.

        Returns:
            List of InstanceMeta, one per registered profile. Empty if none exist.
        """
        if not self._root.exists():
            return []
        profiles: list[InstanceMeta] = []
        for meta_file in sorted(self._root.glob(f"*/{_META}")):
            try:
                profiles.append(
                    InstanceMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))
                )
            except OSError, ValueError, ValidationError:
                log.warning("skipping malformed meta.json: %s", meta_file)
        return profiles

    def load_snapshot(self, profile: str) -> InstanceSnapshot | None:
        """Read snapshot.json for a profile if it exists.

        Args:
            profile: Profile name.

        Returns:
            InstanceSnapshot or None if the profile exists but no snapshot captured yet.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        snap_file = profile_dir / _SNAPSHOT
        if not snap_file.exists():
            return None
        return InstanceSnapshot.model_validate_json(snap_file.read_text(encoding="utf-8"))

    def save_snapshot(self, profile: str, snapshot: InstanceSnapshot) -> None:
        """Atomically write snapshot.json for a profile.

        Writes to a temp file then renames to avoid partial writes on failure.

        Args:
            profile: Profile name.
            snapshot: Snapshot to persist.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        snap_file = profile_dir / _SNAPSHOT
        fd, tmp = tempfile.mkstemp(dir=profile_dir, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(snapshot.model_dump_json(indent=2))
            Path(tmp).replace(snap_file)
        except OSError:
            Path(tmp).unlink(missing_ok=True)
            raise

    def load_plugin_inventory(self, profile: str) -> PluginInventory | None:
        """Read plugins.json for a profile if it exists.

        Args:
            profile: Profile name.

        Returns:
            PluginInventory or None if the profile exists but no inventory captured yet.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        inv_file = profile_dir / _PLUGIN_INVENTORY
        if not inv_file.exists():
            return None
        return PluginInventory.model_validate_json(inv_file.read_text(encoding="utf-8"))

    def save_plugin_inventory(self, profile: str, inventory: PluginInventory) -> None:
        """Atomically write plugins.json for a profile.

        Writes to a temp file then renames to avoid partial writes on failure.

        Args:
            profile: Profile name.
            inventory: Plugin inventory to persist.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        inv_file = profile_dir / _PLUGIN_INVENTORY
        fd, tmp = tempfile.mkstemp(dir=profile_dir, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(inventory.model_dump_json(indent=2))
            Path(tmp).replace(inv_file)
        except OSError:
            Path(tmp).unlink(missing_ok=True)
            raise

    def load_plugin_baseline(self, profile: str) -> PluginInventory | None:
        """Read plugins.baseline.json for a profile if it exists.

        Args:
            profile: Profile name.

        Returns:
            PluginInventory or None if no baseline has been ack'd yet.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        baseline_file = profile_dir / _PLUGIN_BASELINE
        if not baseline_file.exists():
            return None
        return PluginInventory.model_validate_json(baseline_file.read_text(encoding="utf-8"))

    def save_plugin_baseline(self, profile: str, inventory: PluginInventory) -> None:
        """Atomically write plugins.baseline.json for a profile.

        Writes to a temp file then renames to avoid partial writes on failure.

        Args:
            profile: Profile name.
            inventory: Inventory to record as the ack'd baseline.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        baseline_file = profile_dir / _PLUGIN_BASELINE
        fd, tmp = tempfile.mkstemp(dir=profile_dir, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(inventory.model_dump_json(indent=2))
            Path(tmp).replace(baseline_file)
        except OSError:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _dir(self, profile: str) -> Path:
        return self._root / profile
