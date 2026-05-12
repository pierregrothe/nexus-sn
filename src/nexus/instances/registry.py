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
from typing import cast

import yaml
from pydantic import ValidationError

from nexus.instances.errors import InstanceNotFoundError
from nexus.instances.models import InstanceMeta, InstanceSnapshot
from nexus.plugins.baselines import validate_baseline_name
from nexus.plugins.errors import BaselineNotFoundError
from nexus.plugins.models import PluginInventory
from nexus.plugins.overrides import AdvisoryOverrideSet

log = logging.getLogger(__name__)

__all__ = ["InstanceRegistry"]

_META = "meta.json"
_SNAPSHOT = "snapshot.json"
_PLUGIN_INVENTORY = "plugins.json"
_PLUGIN_BASELINE = "plugins.baseline.json"
_ADVISORY_OVERRIDES = "advisory-overrides.yaml"
_BASELINES_DIR = "baselines"


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

    def load_plugin_baseline(self, profile: str, name: str) -> PluginInventory | None:
        """Read a named baseline file. Returns None if absent.

        Logs a WARNING and ignores any legacy plugins.baseline.json
        present in the profile directory.

        Args:
            profile: Profile name.
            name: Baseline name (must pass validate_baseline_name).

        Returns:
            Validated PluginInventory, or None when the file is missing
            or has a stale schema.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
            InvalidBaselineNameError: If ``name`` is not a safe filename.
        """
        validate_baseline_name(name)
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        self._warn_legacy_baseline(profile, profile_dir)
        baseline_file = profile_dir / _BASELINES_DIR / f"{name}.json"
        if not baseline_file.exists():
            return None
        try:
            return PluginInventory.model_validate_json(baseline_file.read_text(encoding="utf-8"))
        except ValidationError:
            log.warning(
                "baselines/%s.json schema outdated for profile=%s -- "
                "run 'nexus plugins drift --ack --baseline %s' to rebuild",
                name,
                profile,
                name,
            )
            return None

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

    def save_plugin_baseline(self, profile: str, name: str, inventory: PluginInventory) -> None:
        """Atomically write a named baseline file under baselines/.

        Args:
            profile: Profile name.
            name: Baseline name (must pass validate_baseline_name).
            inventory: Inventory to record as the named baseline.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
            InvalidBaselineNameError: If ``name`` is not a safe filename.
        """
        validate_baseline_name(name)
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        baselines_dir = profile_dir / _BASELINES_DIR
        baselines_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write_to(baselines_dir / f"{name}.json", inventory.model_dump_json(indent=2))

    def list_plugin_baselines(self, profile: str) -> tuple[str, ...]:
        """Return the names of all baselines for a profile, sorted ascending.

        Args:
            profile: Profile name.

        Returns:
            Tuple of baseline names. Empty tuple when the baselines/ dir is
            absent or contains no .json files.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        self._warn_legacy_baseline(profile, profile_dir)
        baselines_dir = profile_dir / _BASELINES_DIR
        if not baselines_dir.exists():
            return ()
        return tuple(sorted(p.stem for p in baselines_dir.glob("*.json")))

    def list_plugin_baseline_summaries(self, profile: str) -> tuple[tuple[str, str, int], ...]:
        """Return one-line summaries of every baseline for a profile.

        Avoids the full PluginInventory parse done by ``load_plugin_baseline``
        when only ``(name, captured_at, plugin_count)`` is needed -- e.g.,
        ``nexus plugins baselines list``.

        Returns:
            Tuple of ``(name, captured_at_iso, plugin_count)`` sorted by name.
            Entries with malformed JSON are skipped.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
        """
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        baselines_dir = profile_dir / _BASELINES_DIR
        if not baselines_dir.exists():
            return ()
        summaries: list[tuple[str, str, int]] = []
        for path in sorted(baselines_dir.glob("*.json")):
            try:
                raw: object = json.loads(path.read_text(encoding="utf-8"))
            except OSError, json.JSONDecodeError:
                continue
            if not isinstance(raw, dict):
                continue
            data = cast("dict[str, object]", raw)
            captured_obj = data.get("captured_at", "")
            captured = captured_obj if isinstance(captured_obj, str) else ""
            plugins_obj = data.get("plugins", [])
            count = (
                sum(1 for _ in cast("list[object]", plugins_obj))
                if isinstance(plugins_obj, list)
                else 0
            )
            summaries.append((path.stem, captured, count))
        return tuple(summaries)

    def delete_plugin_baseline(self, profile: str, name: str) -> None:
        """Remove a named baseline.

        Args:
            profile: Profile name.
            name: Baseline name to delete.

        Raises:
            InstanceNotFoundError: If the profile directory does not exist.
            InvalidBaselineNameError: If ``name`` is not a safe filename.
            BaselineNotFoundError: If the named baseline file does not exist.
        """
        validate_baseline_name(name)
        profile_dir = self._dir(profile)
        if not profile_dir.exists():
            raise InstanceNotFoundError(profile)
        baseline_file = profile_dir / _BASELINES_DIR / f"{name}.json"
        if not baseline_file.exists():
            raise BaselineNotFoundError(profile, name)
        baseline_file.unlink()

    def _warn_legacy_baseline(self, profile: str, profile_dir: Path) -> None:
        """Emit a one-line WARNING when plugins.baseline.json is present.

        Args:
            profile: Profile name (used in the warning message).
            profile_dir: Resolved profile directory path.
        """
        legacy = profile_dir / _PLUGIN_BASELINE
        if legacy.exists():
            log.warning(
                "legacy plugins.baseline.json for profile=%s is ignored; "
                "re-ack via 'nexus plugins drift --ack' to create a named baseline",
                profile,
            )

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
        self._atomic_write_to(profile_dir / filename, payload)

    def _atomic_write_to(self, target: Path, payload: str) -> None:
        """Write ``payload`` to ``target`` via tempfile-in-parent + rename.

        The temp file is created in the target's parent directory so the
        final rename stays within the same filesystem (atomic on POSIX
        and Windows).
        """
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            Path(tmp).replace(target)
        except OSError:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _dir(self, profile: str) -> Path:
        return self._root / profile
