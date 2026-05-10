# tests/capture/fakes/fake_capture_engine.py
# In-memory fake for CaptureProtocol used in CLI and TUI tests.
# Author: Pierre Grothe
# Date: 2026-05-09

"""FakeCaptureEngine: canned responses for CaptureProtocol consumers."""

from datetime import UTC, datetime
from pathlib import Path

from nexus.capture.models import (
    ArchiveManifest,
    CaptureResult,
    ScopeManifest,
    UpdateSetRef,
)

__all__ = ["FakeCaptureEngine"]

_NOW = datetime(2026, 5, 9, 14, 0, 0, tzinfo=UTC)


class FakeCaptureEngine:
    """In-memory substitute for CaptureEngine in CLI and TUI tests.

    Preload ``scope_manifest``, ``capture_result``, ``archive_manifest``,
    and ``update_set_ref`` attributes to control what each method returns.
    """

    def __init__(self) -> None:
        """Initialize with default empty responses."""
        self.scope_manifest = ScopeManifest(
            instance_id="fake-instance",
            captured_at=_NOW,
            scopes=(),
        )
        self.capture_result = CaptureResult(
            instance_id="fake-instance",
            captured_at=_NOW,
            scope_ids=(),
            table_group="ai_automation",
            records=(),
        )
        self.archive_manifest = ArchiveManifest(
            format_version="1.0",
            instance_id="fake-instance",
            captured_at=_NOW,
            scope_ids=(),
            table_group="ai_automation",
            record_count=0,
            archive_dir=Path("/tmp/fake-archive"),
        )
        self.update_set_ref = UpdateSetRef(
            sys_id="fake-us-001",
            name="NEXUS-fake",
            state="in progress",
            record_count=0,
            instance_id="fake-instance",
        )

    async def discover_scopes(
        self,
        instance_id: str,
        table_group: str = "ai_automation",
        *,
        on_progress: object = None,
    ) -> ScopeManifest:
        """Return the preset scope manifest.

        Args:
            instance_id: Ignored -- returns preset manifest.
            table_group: Ignored.
            on_progress: Ignored.

        Returns:
            The preset ScopeManifest.
        """
        return self.scope_manifest

    async def capture(
        self,
        instance_id: str,
        scope_ids: list[str],
        table_group: str = "ai_automation",
        *,
        on_progress: object = None,
    ) -> CaptureResult:
        """Return the preset capture result.

        Args:
            instance_id: Ignored.
            scope_ids: Ignored.
            table_group: Ignored.

        Returns:
            The preset CaptureResult.
        """
        return self.capture_result

    def save_archive(self, result: CaptureResult, dest: Path | None = None) -> ArchiveManifest:
        """Return the preset archive manifest without writing to disk.

        Args:
            result: Ignored.
            dest: Ignored.

        Returns:
            The preset ArchiveManifest.
        """
        return self.archive_manifest

    def load_archive(self, manifest_path: Path) -> CaptureResult:
        """Return the preset capture result without reading from disk.

        Args:
            manifest_path: Ignored.

        Returns:
            The preset CaptureResult.
        """
        return self.capture_result

    async def push_to_update_set(
        self, result: CaptureResult, instance_id: str, update_set_name: str
    ) -> UpdateSetRef:
        """Return the preset update set ref without making SN calls.

        Args:
            result: Ignored.
            instance_id: Ignored.
            update_set_name: Ignored.

        Returns:
            The preset UpdateSetRef.
        """
        return self.update_set_ref
