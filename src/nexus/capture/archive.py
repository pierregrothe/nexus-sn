# src/nexus/capture/archive.py
# YAML archive writer and reader for captured ServiceNow configurations.
# Author: Pierre Grothe
# Date: 2026-05-09

"""ArchiveWriter and ArchiveReader for persisting CaptureResult to YAML."""

import logging
from pathlib import Path

import yaml

from nexus.capture.errors import ArchiveCorruptError
from nexus.capture.models import ArchiveManifest, CaptureResult, ConfigRecord

log = logging.getLogger(__name__)

__all__ = ["ArchiveReader", "ArchiveWriter"]

_FORMAT_VERSION = "1.0"


class ArchiveWriter:
    """Serializes a CaptureResult to a YAML directory structure.

    Args:
        archive_root: Root directory under which per-instance archives are written.
    """

    def __init__(self, archive_root: Path) -> None:
        """Initialize with the root directory for all archives."""
        self._root = archive_root

    def write(self, result: CaptureResult, dest: Path | None = None) -> ArchiveManifest:
        """Write a CaptureResult to disk as YAML files.

        Args:
            result: The capture result to persist.
            dest: Optional override for the archive directory.

        Returns:
            ArchiveManifest with location and record count.
        """
        if dest is None:
            timestamp = result.captured_at.strftime("%Y%m%d-%H%M%S")
            dest = self._root / result.instance_id / timestamp
        dest.mkdir(parents=True, exist_ok=True)

        root_dirs: dict[str, Path] = {}
        root_records = [r for r in result.records if r.parent_sys_id is None]
        child_records = [r for r in result.records if r.parent_sys_id is not None]

        for record in root_records:
            record_dir = dest / record.table
            record_dir.mkdir(parents=True, exist_ok=True)
            _write_yaml(record, record_dir / f"{record.sys_id}.yaml")
            root_dirs[record.sys_id] = record_dir

        for record in child_records:
            if record.parent_sys_id and record.parent_sys_id in root_dirs:
                parent_dir = root_dirs[record.parent_sys_id]
                child_dir = parent_dir / record.parent_sys_id / record.table
            else:
                child_dir = dest / record.table
            child_dir.mkdir(parents=True, exist_ok=True)
            _write_yaml(record, child_dir / f"{record.sys_id}.yaml")

        manifest = ArchiveManifest(
            format_version=_FORMAT_VERSION,
            instance_id=result.instance_id,
            captured_at=result.captured_at,
            scope_ids=result.scope_ids,
            table_group=result.table_group,
            record_count=len(result.records),
            archive_dir=dest,
        )
        (dest / "manifest.yaml").write_text(
            yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
        log.info("archive written: %s (%d records)", dest, manifest.record_count)
        return manifest


class ArchiveReader:
    """Deserializes a YAML archive back into a CaptureResult."""

    def read(self, manifest_path: Path) -> CaptureResult:
        """Read an archive from disk.

        Args:
            manifest_path: Path to manifest.yaml inside an archive directory.

        Returns:
            CaptureResult reconstructed from YAML.

        Raises:
            ArchiveCorruptError: If manifest is missing or YAML is invalid.
        """
        if not manifest_path.exists():
            raise ArchiveCorruptError(archive_dir=manifest_path.parent)
        try:
            raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            manifest = ArchiveManifest.model_validate(raw, strict=False)
        except Exception as exc:
            raise ArchiveCorruptError(archive_dir=manifest_path.parent) from exc

        archive_dir = manifest_path.parent
        records: list[ConfigRecord] = []
        for yaml_path in sorted(archive_dir.rglob("*.yaml")):
            if yaml_path.name == "manifest.yaml":
                continue
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                records.append(ConfigRecord.model_validate(data, strict=False))
            except Exception as exc:
                log.warning("skipping corrupt record %s: %s", yaml_path, exc)

        return CaptureResult(
            instance_id=manifest.instance_id,
            captured_at=manifest.captured_at,
            scope_ids=manifest.scope_ids,
            table_group=manifest.table_group,
            records=tuple(records),
        )


def _write_yaml(record: ConfigRecord, path: Path) -> None:
    path.write_text(
        yaml.safe_dump(record.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
