# src/nexus/capture/protocol.py
# Public protocol surface for the capture layer.
# Author: Pierre Grothe
# Date: 2026-05-09

"""CaptureProtocol: the interface CLI, TUI, and Web UI bind to."""

from pathlib import Path
from typing import Protocol

from nexus.capture.models import (
    ArchiveManifest,
    CaptureResult,
    ScopeManifest,
    UpdateSetRef,
)
from nexus.capture.tables import AI_AUTOMATION

__all__ = ["CaptureProtocol"]

_DEFAULT_GROUP = AI_AUTOMATION.key


class CaptureProtocol(Protocol):
    """Bidirectional ServiceNow configuration transport."""

    async def discover_scopes(
        self,
        instance_id: str,
        table_group: str = _DEFAULT_GROUP,
    ) -> ScopeManifest:
        """Discover all application scopes on the instance with per-table counts.

        Args:
            instance_id: Registered instance profile name.
            table_group: Which table group to count records for.

        Returns:
            ScopeManifest listing all scopes and per-table record counts.
        """
        ...

    async def capture(
        self,
        instance_id: str,
        scope_ids: list[str],
        table_group: str = _DEFAULT_GROUP,
    ) -> CaptureResult:
        """Fetch all custom configurations in the given scopes from a live instance.

        Tables that return HTTP 400/404 are skipped with a warning.

        Args:
            instance_id: Registered instance profile name.
            scope_ids: sys_id values of application scopes to capture.
            table_group: Which table group to scan.

        Returns:
            CaptureResult with all matching records.
        """
        ...

    def save_archive(
        self,
        result: CaptureResult,
        dest: Path | None = None,
    ) -> ArchiveManifest:
        """Serialize a CaptureResult to YAML on disk.

        Args:
            result: The result to persist.
            dest: Archive root directory. Defaults to
                  ~/.nexus/archives/{instance_id}/{timestamp}/.

        Returns:
            ArchiveManifest with archive location and record count.
        """
        ...

    def load_archive(self, manifest_path: Path) -> CaptureResult:
        """Deserialize a previously saved archive into a CaptureResult.

        Args:
            manifest_path: Path to manifest.yaml inside an archive directory.

        Returns:
            CaptureResult reconstructed from YAML.

        Raises:
            ArchiveCorruptError: If the manifest is missing or YAML is invalid.
        """
        ...

    async def push_to_update_set(
        self,
        result: CaptureResult,
        instance_id: str,
        update_set_name: str,
    ) -> UpdateSetRef:
        """Inject all records from a CaptureResult into an update set.

        Creates the update set if it does not exist. Reuses an in-progress
        update set with the same name if one is found.

        Args:
            result: CaptureResult to deploy.
            instance_id: Target registered instance profile.
            update_set_name: Name for the update set on the target.

        Returns:
            UpdateSetRef for the created or updated update set.

        Raises:
            UpdateSetError: If any record injection fails (fails fast).
        """
        ...
