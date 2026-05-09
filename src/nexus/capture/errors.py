# src/nexus/capture/errors.py
# Capture layer error hierarchy.
# Author: Pierre Grothe
# Date: 2026-05-09

"""Typed exceptions for the capture layer."""

from pathlib import Path

__all__ = [
    "ArchiveCorruptError",
    "CaptureError",
    "ScopeNotFoundError",
    "TableUnavailableError",
    "UpdateSetError",
]


class CaptureError(Exception):
    """Base class for all capture layer errors."""


class ScopeNotFoundError(CaptureError):
    """Requested application scope not found on the instance."""

    def __init__(self, scope_id: str, instance_id: str) -> None:
        """Initialize with scope and instance identifiers."""
        super().__init__(f"Scope {scope_id!r} not found on {instance_id!r}")
        self.scope_id = scope_id
        self.instance_id = instance_id


class TableUnavailableError(CaptureError):
    """Table returned HTTP 400/404 -- absent on this instance (e.g. PDI)."""

    def __init__(self, table: str, instance_id: str) -> None:
        """Initialize with table name and instance identifier."""
        super().__init__(f"Table {table!r} unavailable on {instance_id!r}")
        self.table = table
        self.instance_id = instance_id


class ArchiveCorruptError(CaptureError):
    """Archive manifest missing or YAML invalid."""

    def __init__(self, archive_dir: Path) -> None:
        """Initialize with archive directory path."""
        super().__init__(f"Archive corrupt or missing manifest: {archive_dir}")
        self.archive_dir = archive_dir


class UpdateSetError(CaptureError):
    """Failed to inject a record into the target update set."""

    def __init__(
        self,
        update_set_name: str,
        instance_id: str,
        failed_record_sys_id: str,
        failed_table: str,
    ) -> None:
        """Initialize with update set and record identifiers."""
        super().__init__(
            f"Failed to inject {failed_table}/{failed_record_sys_id} "
            f"into update set {update_set_name!r} on {instance_id!r}"
        )
        self.update_set_name = update_set_name
        self.instance_id = instance_id
        self.failed_record_sys_id = failed_record_sys_id
        self.failed_table = failed_table
