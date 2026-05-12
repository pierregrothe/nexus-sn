# src/nexus/instances/registry.py
# CRUD operations on the per-instance directory tree.
# Author: Pierre Grothe
# Date: 2026-05-08
"""InstanceRegistry: manages ~/.nexus/instances/<profile>/ directories."""

import json
import logging
import shutil
import tempfile
from pathlib import Path

import yaml
from pydantic import ValidationError

from nexus.instances.errors import InstanceNotFoundError
from nexus.instances.models import InstanceMeta, InstanceSnapshot
from nexus.plugins.models import PluginInventory
from nexus.plugins.overrides import AdvisoryOverrideSet

log = logging.getLogger(__name__)

__all__ = ["InstanceRegistry"]

_META = "meta.json"
_SNAPSHOT = "snapshot.json"
_PLUGIN_INVENTORY = "plugins.json"
_PLUGIN_BASELINE = "plugins.baseline.json"
_ADVISORY_OVERRIDES = "advisory-overrides.yaml"


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

        Args:
            profile: Profile name.
            snapshot: Snapshot to persist.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        self._atomic_write(profile, _SNAPSHOT, snapshot.model_dump_json(indent=2))

    def load_plugin_inventory(self, profile: str) -> PluginInventory | None:
        """Read plugins.json for a profile if it exists.

        Args:
            profile: Profile name.

        Returns:
            PluginInventory or None if the profile exists but no inventory
            captured yet -- or if the on-disk file is unreadable / has a
            stale schema (caller is told via WARNING log to refresh).

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        return self._load_plugin_file(
            profile, _PLUGIN_INVENTORY, "run 'nexus instance refresh' to rebuild"
        )

    def save_plugin_inventory(self, profile: str, inventory: PluginInventory) -> None:
        """Atomically write plugins.json for a profile.

        Args:
            profile: Profile name.
            inventory: Plugin inventory to persist.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        self._atomic_write(profile, _PLUGIN_INVENTORY, inventory.model_dump_json(indent=2))

    def load_plugin_baseline(self, profile: str) -> PluginInventory | None:
        """Read plugins.baseline.json for a profile if it exists.

        Args:
            profile: Profile name.

        Returns:
            PluginInventory or None if no baseline has been ack'd yet --
            or if the on-disk file is unreadable / has a stale schema
            (caller is told via WARNING log to re-ack the baseline).

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        return self._load_plugin_file(
            profile, _PLUGIN_BASELINE, "run 'nexus plugins drift --ack' to re-ack the baseline"
        )

    def _load_plugin_file(
        self, profile: str, filename: str, refresh_hint: str
    ) -> PluginInventory | None:
        """Shared loader: read+validate a PluginInventory file, log on schema mismatch.

        Args:
            profile: Profile name.
            filename: File under the profile directory (e.g. ``plugins.json``).
            refresh_hint: One-line action sentence appended to the WARNING log
                when the file fails Pydantic validation.

        Returns:
            ``None`` when the file is missing or has a stale schema. The
            validated PluginInventory otherwise.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        file_path = profile_dir / filename
        if not file_path.exists():
            return None
        try:
            return PluginInventory.model_validate_json(file_path.read_text(encoding="utf-8"))
        except ValidationError:
            log.warning("%s schema outdated for profile=%s -- %s", filename, profile, refresh_hint)
            return None

    def save_plugin_baseline(self, profile: str, inventory: PluginInventory) -> None:
        """Atomically write plugins.baseline.json for a profile.

        Args:
            profile: Profile name.
            inventory: Inventory to record as the ack'd baseline.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        self._atomic_write(profile, _PLUGIN_BASELINE, inventory.model_dump_json(indent=2))

    def load_advisory_overrides(self, profile: str) -> AdvisoryOverrideSet:
        """Read advisory-overrides.yaml for a profile, or return an empty set.

        Args:
            profile: Profile name.

        Returns:
            AdvisoryOverrideSet with the persisted overrides, or an empty set
            when the file is missing or has a stale schema. Schema mismatches
            log a WARNING.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        file_path = profile_dir / _ADVISORY_OVERRIDES
        if not file_path.exists():
            return AdvisoryOverrideSet(overrides=())
        try:
            raw_obj: object = yaml.safe_load(file_path.read_text(encoding="utf-8"))
            payload: str = json.dumps(raw_obj) if isinstance(raw_obj, dict) else "{}"
            return AdvisoryOverrideSet.model_validate_json(payload)
        except yaml.YAMLError, ValidationError:
            log.warning(
                "advisory-overrides.yaml schema outdated for profile=%s -- "
                "edit by hand or remove the file",
                profile,
            )
            return AdvisoryOverrideSet(overrides=())

    def save_advisory_overrides(self, profile: str, overrides: AdvisoryOverrideSet) -> None:
        """Atomically write advisory-overrides.yaml for a profile.

        Args:
            profile: Profile name.
            overrides: Override set to persist.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        payload = yaml.safe_dump(overrides.model_dump(mode="json"), sort_keys=False)
        self._atomic_write(profile, _ADVISORY_OVERRIDES, payload)

    def _atomic_write(self, profile: str, filename: str, payload: str) -> None:
        """Write ``payload`` to ``<profile_dir>/<filename>`` via tmp-and-rename.

        Args:
            profile: Profile name.
            filename: Target file name relative to the profile directory.
            payload: UTF-8 text content to write.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        target = profile_dir / filename
        fd, tmp = tempfile.mkstemp(dir=profile_dir, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            Path(tmp).replace(target)
        except OSError:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _dir(self, profile: str) -> Path:
        return self._root / profile
