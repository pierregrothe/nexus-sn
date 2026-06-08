# src/nexus/schema/archive.py
# JSON snapshot writer/reader for SchemaGraph.
# Author: Pierre Grothe
# Date: 2026-06-08
"""Persist and reload SchemaGraph snapshots under the schema archive root."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from nexus.schema.errors import SchemaArchiveError
from nexus.schema.models import SchemaGraph

__all__ = ["SchemaArchiveReader", "SchemaArchiveWriter"]


class SchemaArchiveWriter:
    """Writes SchemaGraph snapshots as JSON under a root directory.

    Args:
        root: Archive root (e.g. NexusPaths.schema_dir).
    """

    def __init__(self, root: Path) -> None:
        """Initialize with the archive root."""
        self._root = root

    def write(self, graph: SchemaGraph) -> Path:
        """Serialize a graph to ``{root}/{instance}/{area}-{ts}.json``.

        Args:
            graph: The graph to persist.

        Returns:
            Path to the written JSON file.
        """
        stamp = graph.discovered_at.strftime("%Y%m%d-%H%M%S")
        dest_dir = self._root / graph.instance_id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{graph.area_key}-{stamp}.json"
        dest.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
        return dest


class SchemaArchiveReader:
    """Reads SchemaGraph snapshots back from JSON."""

    def read(self, path: Path) -> SchemaGraph:
        """Deserialize a snapshot.

        Args:
            path: Path to a snapshot JSON file.

        Returns:
            The reconstructed SchemaGraph.

        Raises:
            SchemaArchiveError: If the file is missing or invalid.
        """
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SchemaArchiveError(path) from exc
        try:
            return SchemaGraph.model_validate_json(raw)
        except ValidationError as exc:
            raise SchemaArchiveError(path) from exc
