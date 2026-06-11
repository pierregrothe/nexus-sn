# src/nexus/schema/product_registry.py
# Reads and writes the schema product catalog cache.
# Author: Pierre Grothe
# Date: 2026-06-11
"""ProductRegistry: load/save/resolve SchemaProductCatalog from disk."""

from __future__ import annotations

import importlib.resources
import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from nexus.config.types import UtcDatetime
from nexus.schema.products import SchemaProduct, SchemaProductCatalog
from nexus.schema.sync import SchemaSyncSource

log = logging.getLogger(__name__)

__all__ = ["CachedSchemaProductCatalog", "ProductRegistry"]

_CONFIG = ConfigDict(frozen=True, strict=True, extra="forbid")
_CATALOG_FILE = "catalog.json"


class CachedSchemaProductCatalog(BaseModel):
    """On-disk wrapper that adds provenance and timestamp to a catalog.

    Args:
        catalog: The catalog payload.
        source: Repo / branch / path the catalog was fetched from.
        cached_at: UTC timestamp the cache was written.
    """

    model_config = _CONFIG

    catalog: SchemaProductCatalog
    source: SchemaSyncSource
    cached_at: UtcDatetime


class ProductRegistry:
    """Owns the on-disk schema product catalog cache.

    Args:
        schema_dir: Filesystem directory for the cache.
            Typically ``NexusPaths.schema_dir``.
    """

    def __init__(self, schema_dir: Path) -> None:
        """See class docstring."""
        self._dir = schema_dir

    def load_catalog(self) -> SchemaProductCatalog:
        """Return the synced catalog, or the bundled default if no sync yet.

        Returns:
            A valid SchemaProductCatalog; never raises.
        """
        cached = self.load_cached()
        if cached is not None:
            return cached.catalog
        return self._load_bundled()

    def load_cached(self) -> CachedSchemaProductCatalog | None:
        """Read the on-disk cache. Returns None when absent or unreadable.

        Returns:
            The cached entry, or None.
        """
        target = self._dir / _CATALOG_FILE
        if not target.exists():
            return None
        try:
            payload = target.read_text(encoding="utf-8")
        except OSError as exc:
            log.warning("schema catalog read failed (%s): %s", type(exc).__name__, exc)
            return None
        try:
            return CachedSchemaProductCatalog.model_validate_json(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("schema catalog invalid (%s): %s", type(exc).__name__, exc)
            return None

    def save_catalog(
        self, catalog: SchemaProductCatalog, source: SchemaSyncSource
    ) -> CachedSchemaProductCatalog:
        """Atomically persist catalog + source to disk.

        Args:
            catalog: The catalog to persist.
            source: Provenance record.

        Returns:
            The CachedSchemaProductCatalog that was written.

        Raises:
            OSError: If the directory cannot be created or file cannot be written.
        """
        self._dir.mkdir(parents=True, exist_ok=True)
        cached = CachedSchemaProductCatalog(
            catalog=catalog,
            source=source,
            cached_at=datetime.now(UTC),
        )
        target = self._dir / _CATALOG_FILE
        fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(cached.model_dump_json(indent=2))
            Path(tmp_path).replace(target)
        except OSError:
            Path(tmp_path).unlink(missing_ok=True)
            raise
        log.info(
            "schema catalog cached: source=%s/%s/%s entries=%d",
            source.repo,
            source.branch,
            source.path,
            len(catalog.products),
        )
        return cached

    def resolve(self, ref: str) -> SchemaProduct | None:
        """Resolve a product reference using the best available catalog.

        Args:
            ref: Key, acronym, or full product name.

        Returns:
            The matching SchemaProduct, or None.
        """
        return self.load_catalog().resolve(ref)

    @staticmethod
    def _load_bundled() -> SchemaProductCatalog:
        """Load the bundled products.json shipped with the package.

        Returns:
            The bundled SchemaProductCatalog.
        """
        data = (
            importlib.resources.files("nexus.schema")
            .joinpath("products.json")
            .read_text(encoding="utf-8")
        )
        return SchemaProductCatalog.model_validate_json(data)
