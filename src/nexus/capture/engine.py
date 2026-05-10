# src/nexus/capture/engine.py
# CaptureEngine: orchestrates all capture layer components.
# Author: Pierre Grothe
# Date: 2026-05-09

"""CaptureEngine: concrete implementation of CaptureProtocol."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from nexus.capture.archive import ArchiveReader, ArchiveWriter
from nexus.capture.fetcher import ConfigFetcher
from nexus.capture.models import (
    ArchiveManifest,
    CaptureResult,
    ScopeManifest,
    UpdateSetRef,
)
from nexus.capture.scope import ScopeDiscoverer
from nexus.capture.tables import AI_AUTOMATION, DEFAULT_TABLE_GROUPS, TableGroup
from nexus.capture.update_set import UpdateSetWriter
from nexus.capture.xml_builder import UpdateSetXmlBuilder
from nexus.connectors.servicenow.client import ServiceNowClient

log = logging.getLogger(__name__)

__all__ = ["CaptureEngine"]


class CaptureEngine:
    """Bidirectional ServiceNow configuration transport.

    Implements CaptureProtocol. Wires ScopeDiscoverer, ConfigFetcher,
    ArchiveWriter/Reader, and UpdateSetWriter. Callers inject a
    ServiceNowClient; the engine never constructs one itself.

    Args:
        client: Open ServiceNowClient for the source/target instance.
        archive_root: Root directory for local YAML archives.
        table_groups: Table group registry (defaults to DEFAULT_TABLE_GROUPS).
    """

    def __init__(
        self,
        client: ServiceNowClient,
        archive_root: Path,
        table_groups: dict[str, TableGroup] | None = None,
    ) -> None:
        """Initialize all internal components with the provided dependencies."""
        groups = table_groups or DEFAULT_TABLE_GROUPS
        self._discoverer = ScopeDiscoverer(client, groups)
        self._fetcher = ConfigFetcher(client, groups)
        self._writer = ArchiveWriter(archive_root)
        self._reader = ArchiveReader()
        self._usw = UpdateSetWriter(client, UpdateSetXmlBuilder())

    async def discover_scopes(
        self,
        instance_id: str,
        table_group: str = AI_AUTOMATION.key,
        *,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> ScopeManifest:
        """Discover all application scopes on the instance with per-table counts.

        Args:
            instance_id: Registered instance profile name.
            table_group: Which table group to count records for.
            on_progress: Optional callback (completed, total, message).

        Returns:
            ScopeManifest listing all scopes and per-table record counts.
        """
        return await self._discoverer.discover(instance_id, table_group, on_progress=on_progress)

    async def capture(
        self,
        instance_id: str,
        scope_ids: list[str],
        table_group: str = AI_AUTOMATION.key,
        *,
        on_progress: Callable[[int, int, str], None] | None = None,
    ) -> CaptureResult:
        """Fetch all custom configurations in the given scopes.

        Args:
            instance_id: Registered instance profile name.
            scope_ids: Application scope sys_ids to capture.
            table_group: Which table group to scan.
            on_progress: Optional callback (completed, total, message).

        Returns:
            CaptureResult with all matching records.
        """
        records = await self._fetcher.fetch(
            instance_id, scope_ids, table_group, on_progress=on_progress
        )
        return CaptureResult(
            instance_id=instance_id,
            captured_at=datetime.now(UTC),
            scope_ids=tuple(scope_ids),
            table_group=table_group,
            records=tuple(records),
        )

    def save_archive(
        self,
        result: CaptureResult,
        dest: Path | None = None,
    ) -> ArchiveManifest:
        """Serialize a CaptureResult to YAML on disk.

        Args:
            result: The capture result to persist.
            dest: Override for the archive directory.

        Returns:
            ArchiveManifest with location and record count.
        """
        return self._writer.write(result, dest)

    def load_archive(self, manifest_path: Path) -> CaptureResult:
        """Deserialize a previously saved archive into a CaptureResult.

        Args:
            manifest_path: Path to manifest.yaml inside an archive directory.

        Returns:
            CaptureResult reconstructed from YAML.

        Raises:
            ArchiveCorruptError: If the manifest is missing or YAML is invalid.
        """
        return self._reader.read(manifest_path)

    async def push_to_update_set(
        self,
        result: CaptureResult,
        instance_id: str,
        update_set_name: str,
    ) -> UpdateSetRef:
        """Inject all records from a CaptureResult into an update set.

        Args:
            result: CaptureResult to deploy.
            instance_id: Target instance profile name.
            update_set_name: Name for the update set.

        Returns:
            UpdateSetRef for the created or reused update set.

        Raises:
            UpdateSetError: If any record injection fails.
        """
        return await self._usw.push(result, instance_id, update_set_name)
