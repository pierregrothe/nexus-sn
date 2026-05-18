# src/nexus/templates/registry.py
# Local cache for the fetched template manifest.
# Author: Pierre Grothe
# Date: 2026-05-18
"""TemplateRegistry: read/write ``~/.nexus/templates/manifest.json``.

Atomic write via tempfile + rename so an interrupted ``nexus sync``
never leaves a partial / unreadable cache. Load returns ``None``
when the cache is absent or unparseable (the orchestrator surfaces
this).
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from nexus.templates.models import CachedManifest

if TYPE_CHECKING:
    from nexus.templates.models import SyncSource, TemplateManifest

log = logging.getLogger(__name__)

__all__ = ["TemplateRegistry"]

_MANIFEST_FILE = "manifest.json"


class TemplateRegistry:
    """Owns the on-disk template-catalog cache.

    Args:
        templates_dir: Filesystem directory under which the cache is
            stored. Typically ``NexusPaths.templates_dir``. Created on
            first ``save_manifest`` if absent.
    """

    def __init__(self, templates_dir: Path) -> None:
        """See class docstring."""
        self._dir = templates_dir

    def save_manifest(self, manifest: TemplateManifest, source: SyncSource) -> CachedManifest:
        """Persist ``manifest`` + ``source`` + a UTC ``cached_at`` stamp.

        Atomic via ``tempfile.mkstemp`` in the parent + ``Path.replace``.
        If the rename fails, the previous cache is unaffected; any
        tempfile is cleaned up before re-raising.

        Args:
            manifest: Wire manifest as fetched from GitHub.
            source: Record of the repo / branch / path used.

        Returns:
            The wrapping ``CachedManifest`` that was persisted.

        Raises:
            OSError: If the directory cannot be created or the file
                cannot be written. Callers (the orchestrator) catch
                this and surface a ``SyncReport`` with the failure
                reason.
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        cached = CachedManifest(wire=manifest, source=source, cached_at=datetime.now(UTC))
        target = self._dir / _MANIFEST_FILE
        fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(cached.model_dump_json(indent=2))
            Path(tmp_path).replace(target)
        except OSError:
            Path(tmp_path).unlink(missing_ok=True)
            raise
        log.info(
            "template manifest cached: source=%s/%s/%s entries=%d",
            source.repo,
            source.branch,
            source.path,
            len(manifest.templates),
        )
        return cached

    def load_manifest(self) -> CachedManifest | None:
        """Read and validate the on-disk manifest. Returns ``None`` if absent or invalid.

        Returns:
            The cached manifest, or ``None`` when:

            * the cache file does not exist,
            * the file cannot be read (logged at ``warning``),
            * the JSON is malformed (logged at ``warning``),
            * the JSON does not match ``CachedManifest`` (logged at
              ``warning``).

            The corrupted file is left in place so the user can inspect.
        """
        target = self._dir / _MANIFEST_FILE
        if not target.exists():
            return None
        try:
            payload = target.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("template manifest read failed (%s): %s", type(exc).__name__, exc)
            return None
        try:
            return CachedManifest.model_validate_json(payload)
        except json.JSONDecodeError as exc:
            log.warning("template manifest invalid JSON: %s", exc)
            return None
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {"loc": (), "type": "unknown"}
            err_type = str(first.get("type", "unknown"))
            if err_type == "json_invalid":
                log.warning("template manifest invalid JSON")
                return None
            loc_parts = first.get("loc", ()) or ()
            loc = ".".join(str(p) for p in loc_parts) or "(root)"
            log.warning("template manifest schema mismatch at %s: %s", loc, err_type)
            return None
