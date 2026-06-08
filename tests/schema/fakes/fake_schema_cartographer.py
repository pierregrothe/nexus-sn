# tests/schema/fakes/fake_schema_cartographer.py
# In-memory SchemaProtocol fake for CLI tests.
# Author: Pierre Grothe
# Date: 2026-06-08
"""FakeSchemaCartographer: canned-graph substitute for SchemaCartographer."""

from __future__ import annotations

from pathlib import Path

from nexus.schema.catalog import MindmapCatalog
from nexus.schema.models import SchemaGraph

__all__ = ["FakeSchemaCartographer"]


class FakeSchemaCartographer:
    """Returns a canned SchemaGraph and round-trips it through JSON.

    Doubles as the async client used in ``async with client`` in CLI tests.

    Args:
        graph: The graph returned by discover() and persisted by save_archive().
    """

    def __init__(self, graph: SchemaGraph, catalog: MindmapCatalog | None = None) -> None:
        """Initialize with the canned graph and optional catalog."""
        self._graph = graph
        self._catalog = catalog

    async def __aenter__(self) -> FakeSchemaCartographer:
        """Enter the async context (returns self)."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Exit the async context (no-op)."""

    async def discover(self, instance_id: str, area_key: str) -> SchemaGraph:
        """Return the canned graph regardless of inputs.

        Args:
            instance_id: Ignored.
            area_key: Ignored.

        Returns:
            The canned SchemaGraph.
        """
        del instance_id, area_key
        return self._graph

    def save_archive(self, graph: SchemaGraph, dest: Path | None = None) -> Path:
        """Write the graph JSON under dest (defaults to cwd) and return the path.

        Args:
            graph: The graph to persist.
            dest: Destination directory; defaults to the current directory.

        Returns:
            Path to the written JSON file.
        """
        root = dest or Path.cwd()
        root.mkdir(parents=True, exist_ok=True)
        path = root / f"{graph.area_key}.json"
        path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load_archive(self, path: Path) -> SchemaGraph:
        """Reload a graph snapshot from JSON.

        Args:
            path: Path to a snapshot JSON file.

        Returns:
            The reconstructed SchemaGraph.
        """
        return SchemaGraph.model_validate_json(path.read_text(encoding="utf-8"))

    def render_erd(self, graph: SchemaGraph) -> str:
        """Return a trivial Markdown stub mentioning the area key.

        Args:
            graph: The graph to render.

        Returns:
            A minimal Markdown string containing the area key.
        """
        return f"# {graph.area_key}\n\nerDiagram"

    async def build_mindmap(self, instance_id: str, area_key: str) -> MindmapCatalog:
        """Return the canned catalog (raises if none was provided).

        Args:
            instance_id: Ignored.
            area_key: Ignored.

        Returns:
            The canned MindmapCatalog.

        Raises:
            ValueError: If the fake was created without a catalog.
        """
        del instance_id, area_key
        if self._catalog is None:
            raise ValueError("FakeSchemaCartographer was created without a catalog")
        return self._catalog

    def render_mindmap(self, catalog: MindmapCatalog) -> str:
        """Return a trivial Markdown stub mentioning the area key.

        Args:
            catalog: The catalog to render.

        Returns:
            A minimal Markdown string containing the area key and 'mindmap'.
        """
        return f"# {catalog.area_key}\n\nmindmap"
